# Project D — Live Demo Runbook

Covers all AC items for **Provision and manage container images in a private registry**.
Repo: `new-user888/peex-registry-security-demo`. Infra deployed in `infra/`.

Current values (deployed 2026-06-23):
- `REPO=new-user888/peex-registry-security-demo`
- `ECR_REPOSITORY_URL=808850080264.dkr.ecr.eu-central-1.amazonaws.com/peex-registry-security`
- `CI_ROLE_ARN=arn:aws:iam::808850080264:role/peex-registry-security-ci-role`

---

## 0. Deploy infra (if destroyed)

```sh
cd infra
terraform init
terraform apply -auto-approve
cd ..

ECR_URL=$(terraform -chdir=infra output -raw ecr_repository_url)
CI_ROLE_ARN=$(terraform -chdir=infra output -raw ci_role_arn)
gh variable set ECR_REPOSITORY_URL --body "$ECR_URL" --repo new-user888/peex-registry-security-demo
gh variable set AWS_CI_ROLE_ARN --body "$CI_ROLE_ARN" --repo new-user888/peex-registry-security-demo
```

If the GitHub repo itself doesn't exist yet:
```sh
git init && git add -A && git commit -m "feat: initial scaffold"
gh repo create new-user888/peex-registry-security-demo --public --source=. --remote=origin
git push -u origin main
```

---

## DEMO FLOW

### 1. RBAC + branch protection on `main`

```sh
gh api repos/new-user888/peex-registry-security-demo/branches/main/protection \
  --jq '{reviews: .required_pull_request_reviews.required_approving_review_count, status_checks: .required_status_checks.contexts, force_push: .allow_force_pushes.enabled, deletions: .allow_deletions.enabled}'
```
Console: GitHub repo → Settings → Branches → `main` rule — shows 1 required approval, required
status check `build-and-push`, force-push and deletion both blocked.

Show `CODEOWNERS` (root of repo) — requires owner review on every path.

---

### 2. Code scanning (CodeQL) — real detection + remediation

```sh
gh api repos/new-user888/peex-registry-security-demo/code-scanning/alerts \
  --jq '.[] | {rule: .rule.id, severity: .rule.severity, state: .state, file: .most_recent_instance.location.path}'
# -> py/command-line-injection: state "fixed"
# -> py/reflective-xss: state "fixed"
```

Console: repo → Security → Code scanning — both alerts visible, marked **Closed (fixed)**.

Show the diff that fixed them:
```sh
git log --oneline | grep remediate
git show --stat <that-commit-sha>
```
`os.system(f"echo Hello {name}")` → `subprocess.run(["echo","Hello",name], shell=False)` +
`escape(name)` before reflecting it back — this is the "vulnerability response process" in code.

---

### 3. Secret scanning + push protection — real blocked push

```sh
gh api repos/new-user888/peex-registry-security-demo --jq '.security_and_analysis'
# -> secret_scanning: enabled, secret_scanning_push_protection: enabled
```

This is the actual rejection captured during setup (reproduce by trying to push a file containing
an `AKIA...` + matching secret key pair):
```
remote: error: GH013: Repository rule violations found for refs/heads/main.
remote: - GITHUB PUSH PROTECTION
remote:   - Push cannot contain secrets
remote:     —— Amazon AWS Access Key ID ——
remote:     —— Amazon AWS Secret Access Key ——
 ! [remote rejected] main -> main (push declined due to repository rule violations)
```
The secret **never reached the remote repository** — push protection blocked it client-side at
the `git push` step, before the commit was even accepted.

> Note: the well-known AWS documentation example key (`AKIAIOSFODNN7EXAMPLE`) is explicitly
> allow-listed by GitHub (too many false positives across the internet) and is **not** blocked —
> a synthetic-but-structurally-valid key was used instead to get a real block.

---

### 4. Dependency scanning (Dependabot) — real alerts + PRs

```sh
gh pr list --repo new-user888/peex-registry-security-demo --state open
# -> 5 open PRs: flask 2.0.1->3.1.3, requests 2.6.0->2.34.2, python base image bump,
#    2x github-actions version bumps

gh api repos/new-user888/peex-registry-security-demo/dependabot/alerts \
  --jq '.[] | {package: .dependency.package.name, severity: .security_advisory.severity, summary: .security_advisory.summary}'
# -> 7 real alerts (2 high, 4 medium, 1 low), e.g.:
#    "Insufficiently Protected Credentials in Requests" (high)
#    "Flask vulnerable to possible disclosure of permanent session cookie ..." (high)
```

Console: repo → Security → Dependabot alerts — full list with CVE/GHSA links.

---

### 5. Private container registry (ECR) — strict access + image scanning

```sh
aws ecr describe-repositories --repository-names peex-registry-security --region eu-central-1 \
  --query "repositories[0].{Url:repositoryUri,ImageTagMutability:imageTagMutability,ScanOnPush:imageScanningConfiguration.scanOnPush}"
```

```sh
aws ecr get-repository-policy --repository-name peex-registry-security --region eu-central-1 \
  --query Policy --output text | python -m json.tool
# -> only peex-registry-security-ci-role principal allowed
```

Console: ECR → Repositories → `peex-registry-security` → Permissions — shows the restricted
policy.

---

### 6. Image vulnerability scan results

```sh
IMAGE_TAG=$(aws ecr describe-images --repository-name peex-registry-security --region eu-central-1 \
  --query "imageDetails[?contains(imageTags[0],'v')] | [0].imageTags[0]" --output text)
# -> v1.0.0 (semver tag, not a commit SHA - bump the root VERSION file before the next release push)

aws ecr describe-image-scan-findings --repository-name peex-registry-security \
  --image-id imageTag=$IMAGE_TAG --region eu-central-1 \
  --query "imageScanFindings.findingSeverityCounts"
# -> {"CRITICAL": 20, "HIGH": 49, "MEDIUM": 36, "LOW": 3}
```

Console: ECR → Repositories → `peex-registry-security` → image → Scan results — full CVE list
with NVD links (e.g. CVE-2021-27645 in glibc, CVE-2022-1664 in dpkg — real OS package CVEs from
the deliberately outdated `python:3.9.0-slim` base image).

---

### 7. OIDC — no static AWS credentials anywhere

```sh
gh secret list --repo new-user888/peex-registry-security-demo
# -> empty: no AWS access keys stored as repo secrets

gh variable list --repo new-user888/peex-registry-security-demo
# -> ECR_REPOSITORY_URL, AWS_CI_ROLE_ARN (ARNs/URLs - not sensitive, fine as plaintext variables)
```

Show the trust policy scoping in `infra/main.tf` (`aws_iam_role.ci`):
```hcl
StringLike = {
  "token.actions.githubusercontent.com:sub" = "repo:new-user888/peex-registry-security-demo:ref:refs/heads/main"
}
```
Only a push to `main` in this exact repo can assume this role — no other workflow, repo, or
branch can use it, even if they had the role ARN.

Watch a real CI run authenticate this way:
```sh
gh run list --repo new-user888/peex-registry-security-demo --workflow=ci.yml --limit 3
gh run view --repo new-user888/peex-registry-security-demo --log | grep -i "Assuming role\|configure-aws-credentials"
```

---

### 8. Branch protection bypass is logged (admin path)

When the maintainer pushes directly (bypassing PR review, since `enforce_admins = false`),
GitHub explicitly logs it on every push:
```
remote: Bypassed rule violations for refs/heads/main:
remote: - Changes must be made through a pull request.
remote: - Required status check "build-and-push" is expected.
```
This is visible audit evidence that the rule exists and was knowingly bypassed by an admin, not
silently ignored.

---

## Teardown

```sh
cd infra
terraform destroy -auto-approve
cd ..
```

The GitHub repository is not managed by Terraform — remove it separately if no longer needed:
```sh
gh repo delete new-user888/peex-registry-security-demo --yes
```
