terraform {
  # use_lockfile (bloqueo nativo del estado en S3) necesita Terraform 1.11 o superior
  required_version = ">= 1.11"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region = "eu-west-1"

  # Etiquetas que se añaden solas a todo lo que cree este código: así, en la
  # factura y en la consola se ve de qué proyecto es cada pieza
  default_tags {
    tags = {
      Project   = "booking-bot"
      ManagedBy = "terraform"
      Stack     = "bootstrap"
    }
  }
}
