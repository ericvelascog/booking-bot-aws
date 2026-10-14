terraform {
  required_version = ">= 1.11"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region = local.region

  default_tags {
    tags = {
      Project   = "booking-bot"
      ManagedBy = "terraform"
      Stack     = "app"
    }
  }
}

# Valores que se repiten en varios archivos de esta carpeta
locals {
  name     = "booking-bot"
  region   = "eu-west-1"
  app_port = 8000
  azs      = ["eu-west-1a", "eu-west-1b"]
}

# "Preguntas" a AWS sobre cosas que ya existen y que esta carpeta no gestiona
data "aws_caller_identity" "current" {} # el número de tu cuenta

data "aws_ecr_repository" "app" { # el almacén creado en infra/bootstrap
  name = "booking-bot"
}
