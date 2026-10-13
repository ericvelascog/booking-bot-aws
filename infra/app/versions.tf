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
  region = "eu-west-1"

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
  app_port = 8000
  azs      = ["eu-west-1a", "eu-west-1b"]
}
