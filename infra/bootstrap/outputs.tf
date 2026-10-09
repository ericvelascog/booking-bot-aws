output "state_bucket" {
  description = "Bucket donde se guarda el estado de Terraform"
  value       = aws_s3_bucket.tfstate.bucket
}
