output "state_bucket" {
  description = "Bucket donde se guarda el estado de Terraform"
  value       = aws_s3_bucket.tfstate.bucket
}

output "github_deploy_role_arn" {
  description = "Rol que asume el pipeline de despliegue (va en deploy.yml)"
  value       = aws_iam_role.github_deploy.arn
}

output "ecr_repository_url" {
  description = "Dirección del almacén de imágenes (para docker push)"
  value       = aws_ecr_repository.app.repository_url
}
