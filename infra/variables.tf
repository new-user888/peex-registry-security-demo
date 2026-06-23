variable "aws_region" {
  default = "eu-central-1"
}

variable "name" {
  default = "peex-registry-security"
}

variable "github_owner" {
  description = "GitHub account/org that owns the repository"
  default     = "new-user888"
}

variable "github_repo" {
  description = "GitHub repository name (without owner)"
  default     = "peex-registry-security-demo"
}
