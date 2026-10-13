output "vpc_id" {
  description = "ID de la VPC"
  value       = aws_vpc.main.id
}

output "public_subnet_ids" {
  description = "IDs de las dos subredes públicas"
  value       = aws_subnet.public[*].id
}
