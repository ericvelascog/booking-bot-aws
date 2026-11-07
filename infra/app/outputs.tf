output "vpc_id" {
  description = "ID de la VPC"
  value       = aws_vpc.main.id
}

output "public_subnet_ids" {
  description = "IDs de las dos subredes públicas"
  value       = aws_subnet.public[*].id
}

output "alb_dns_name" {
  description = "Dirección del ALB. Solo atiende a CloudFront: la URL pública sale de infra/edge"
  value       = aws_lb.main.dns_name
}
