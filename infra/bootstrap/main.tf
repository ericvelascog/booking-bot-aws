# Bucket S3 donde Terraform guarda su "cuaderno" (el estado) de toda la infraestructura

resource "aws_s3_bucket" "tfstate" {
  # El nombre de un bucket es único en todo el mundo, como un dominio web
  bucket = "ericvelascog-booking-bot-tfstate"

  # Candado: Terraform se niega a borrar este bucket, ni siquiera con destroy
  lifecycle {
    prevent_destroy = true
  }
}

# Versionado: cada cambio del estado guarda la versión anterior
resource "aws_s3_bucket_versioning" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  versioning_configuration {
    status = "Enabled"
  }
}

# Cifrado: todo lo que se guarde en el bucket queda cifrado en disco
resource "aws_s3_bucket_server_side_encryption_configuration" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Nadie de internet puede leerlo, aunque alguien se equivoque con los permisos
resource "aws_s3_bucket_public_access_block" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
