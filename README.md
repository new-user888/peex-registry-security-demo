# Project D — Repository & Container Registry Security

Demonstrates secure practices across the artifact lifecycle: source repository RBAC/branch
protection, automated code/secret/dependency scanning, and a private container registry (AWS
ECR) with strict, OIDC-based access control and image vulnerability scanning.

- **Repository**: https://github.com/new-user888/peex-registry-security-demo (public, so GitHub
  Advanced Security features are free)
- **Registry**: AWS ECR `peex-registry-security` (eu-central-1)

## Architecture

```
GitHub repo (branch-protected main)
  -> push to main
       -> GitHub Actions (OIDC, no static AWS keys)
            -> assumes peex-registry-security-ci-role (scoped to this repo + this ref only)
                 -> docker build + push -> ECR repository (scan_on_push = true)
  -> Dependabot (dependency graph + version updates) -> alerts + PRs
  -> CodeQL default setup -> code scanning alerts
  -> Secret scanning + push protection -> blocks pushes containing real-looking credentials
```

## Source repository security

- **Branch protection on `main`**: 1 required PR approval, required status check
  (`build-and-push`), no force-push, no branch deletion, stale reviews dismissed on new commits.
  Configured via `gh api repos/.../branches/main/protection`.
- **RBAC**: repo owner has admin; `CODEOWNERS` requires owner review on all paths. Branch
  protection is enforced for all non-admin contributors — admins can bypass (GitHub always logs
  the bypass, see RUNBOOK step 6), which is the standard, documented model for solo-maintainer
  repos without a paid Enterprise plan that supports `enforce_admins`.
- **Code scanning**: CodeQL default setup (Python). Found 2 real alerts in the first scan
  (`py/command-line-injection`, `py/reflective-xss` in `app/app.py`), both since fixed and
  confirmed closed (`state: fixed`).
- **Secret scanning + push protection**: enabled by default on public repos. A push containing a
  synthetic AWS Access Key ID + Secret Access Key was **rejected by GitHub at the git level**
  (`GH013: Repository rule violations ... Push cannot contain secrets`) — the secret never
  reached the remote repository.
- **Dependency scanning**: `.github/dependabot.yml` covers `pip` (`/app`), `docker` (root
  `Dockerfile`), and `github-actions`. Deliberately outdated `Flask==2.0.1` / `requests==2.6.0`
  triggered 5 real version-update PRs and 7 real Dependabot security alerts (2 high, 4 moderate,
  1 low — e.g. "Insufficiently Protected Credentials in Requests", "Flask vulnerable to possible
  disclosure of permanent session cookie").
- **`.gitignore`**: excludes `__pycache__/`, `.env`, `*.pem`, Terraform state/lock files.

## Container registry security (AWS ECR)

- **Private registry**: `aws_ecr_repository.app`, `image_tag_mutability = IMMUTABLE` (tags can't
  be overwritten once pushed — supply-chain integrity).
- **Versioning**: images are tagged with a semantic version read from the root `VERSION` file
  (e.g. `v1.0.0`), not the commit SHA — easier to identify "what's actually running" than a hash.
  Because the repository is immutable, `VERSION` must be bumped before every push that should
  produce a new image; pushing the same version twice fails on purpose (the immutable tag already
  exists), which is a deliberate guard against silently replacing a released image.
- **Image scanning**: `scan_on_push = true`. The first pushed image (built from the deliberately
  outdated `python:3.9.0-slim` base) was scanned and found **20 CRITICAL, 49 HIGH, 36 MEDIUM, 3
  LOW** real CVEs in OS-level packages (glibc, dpkg, etc.) — a genuine vulnerability scanner
  result, not a placeholder.
- **Least-privilege access**: no IAM user, no long-lived AWS access keys anywhere. GitHub Actions
  authenticates via **OIDC federation** (`aws_iam_openid_connect_provider.github`) and assumes
  `peex-registry-security-ci-role`, whose trust policy is scoped with `StringLike` to
  `repo:new-user888/peex-registry-security-demo:ref:refs/heads/main` only — no other repo, branch,
  or PR can assume this role.
- **Scoped permissions**: the CI role's IAM policy only allows push/pull actions on this one
  repository's ARN (`aws_iam_role_policy.ci_ecr_push`), not `ecr:*` on the whole registry.
  `aws_ecr_repository_policy.app` adds a second, registry-side restriction to the same role —
  defense in depth.
- **Lifecycle policy**: untagged images expire after 14 days (cost control, reduces stale-image
  attack surface).

## Vulnerability response process

1. Automated tools (CodeQL, Dependabot, ECR scan) raise an alert with a severity rating.
2. Triage by severity: CRITICAL/HIGH addressed first (e.g. the command-injection/XSS pair was
   fixed in the very next commit after detection).
3. Fix committed, pushed; the same scanner re-evaluates and the alert is marked `fixed`/closed
   automatically (no manual alert dismissal).
4. Dependency vulnerabilities are handled via the Dependabot version-update PRs already open in
   the repo — reviewed and merged like any other PR (subject to the same branch protection rules).
5. Base-image CVEs (the 20 critical findings) are tracked via the Dependabot `docker` ecosystem
   entry in `dependabot.yml`, which already opened a PR bumping `python:3.9.0-slim` to a current
   patch release.

## Infra (`infra/`)

```sh
cd infra
terraform init
terraform apply
```

Outputs `ecr_repository_url` and `ci_role_arn` are wired into the GitHub repo as **variables**
(`ECR_REPOSITORY_URL`, `AWS_CI_ROLE_ARN`) — visible in plaintext (they're ARNs/URLs, not secrets)
via `gh variable list`, never as a GitHub *secret*, since nothing sensitive needs to be stored.

See `RUNBOOK.md` for the full command-by-command demo sequence and AC coverage table.

Run `terraform destroy` in `infra/` when done. The GitHub repository and its history are not
destroyed by Terraform — delete manually with `gh repo delete` if no longer needed.
