output "vpc_id" {
  description = "ID de la VPC"
  value       = aws_vpc.main.id
}

output "public_subnet_ids" {
  description = "IDs de las dos subredes públicas"
  value       = aws_subnet.public[*].id
}

output "app_url" {
  description = "Dirección pública del bot (la del balanceador)"
  value       = "http://${aws_lb.main.dns_name}"
}
