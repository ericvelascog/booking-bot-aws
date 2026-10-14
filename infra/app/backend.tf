# Mismo bucket que el bootstrap, pero otro cuaderno: app/ en vez de bootstrap/
terraform {
  backend "s3" {
    bucket       = "ericvelascog-booking-bot-tfstate"
    key          = "app/terraform.tfstate"
    region       = "eu-west-1"
    encrypt      = true
    use_lockfile = true
  }
}
