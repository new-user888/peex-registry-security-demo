output "ecr_repository_url" {
  value = aws_ecr_repository.app.repository_url
}

output "ecr_repository_arn" {
  value = aws_ecr_repository.app.arn
}

output "ci_role_arn" {
  value = aws_iam_role.ci.arn
}
 
