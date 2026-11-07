# Tercer cuaderno en el mismo bucket: edge/
terraform {
  backend "s3" {
    bucket       = "ericvelascog-booking-bot-tfstate"
    key          = "edge/terraform.tfstate"
    region       = "eu-west-1"
    encrypt      = true
    use_lockfile = true
  }
}
