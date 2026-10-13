# Dónde guarda Terraform el estado de ESTA carpeta: dentro del bucket que
# crea esta misma carpeta. Primero se aplicó con el estado en local y después
# se migró aquí con `terraform init -migrate-state`.
terraform {
  backend "s3" {
    bucket       = "ericvelascog-booking-bot-tfstate"
    key          = "bootstrap/terraform.tfstate"
    region       = "eu-west-1"
    encrypt      = true
    use_lockfile = true
  }
}
