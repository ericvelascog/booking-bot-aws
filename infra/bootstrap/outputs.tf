output "state_bucket" {
  description = "Bucket donde se guarda el estado de Terraform"
  value       = aws_s3_bucket.tfstate.bucket
}

output "ecr_repository_url" {
  description = "Dirección del almacén de imágenes (para docker push)"
  value       = aws_ecr_repository.app.repository_url
}
