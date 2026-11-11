# Bucket S3 donde Terraform guarda su "cuaderno" (el estado) de toda la infraestructura

resource "aws_s3_bucket" "tfstate" {
  # El nombre de un bucket es único en todo el mundo, como un dominio web
  bucket = "ericvelascog-booking-bot-tfstate"

  # Candado: Terraform se niega a borrar este bucket, ni siquiera con destroy
  lifecycle {
    prevent_destroy = true
  }

  # Avisos de checkov aceptados a propósito. Motivos: docs/security-scanning.md
  # checkov:skip=CKV_AWS_145:Encrypted with SSE-S3 (AES-256); a customer managed KMS key costs 1 USD per month
  # checkov:skip=CKV_AWS_144:Versioning and prevent_destroy protect the state; a replica in another region doubles the cost for a demo
  # checkov:skip=CKV_AWS_18:Every read and write of the state is recorded as a CloudTrail data event instead (cloudtrail.tf)
  # checkov:skip=CKV2_AWS_62:Nothing needs to react when the state changes
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

# Limpieza automática. El versionado guarda para siempre cada versión antigua
# del estado, y también la de cada candado (.tflock): cada plan o apply crea y
# borra uno. Se borran las versiones antiguas de más de 90 días, conservando
# siempre las 10 más recientes de cada archivo por si hay que volver atrás.
resource "aws_s3_bucket_lifecycle_configuration" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  rule {
    id     = "expire-old-versions"
    status = "Enabled"
    filter {} # todo el bucket

    noncurrent_version_expiration {
      noncurrent_days           = 90
      newer_noncurrent_versions = 10
    }

    # Las "marcas de borrado" que se quedan solas cuando ya no queda ninguna versión
    expiration {
      expired_object_delete_marker = true
    }

    # Subidas a medias, por ejemplo de un apply que se cortó
    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }

  # Las reglas de versiones antiguas necesitan el versionado ya activado
  depends_on = [aws_s3_bucket_versioning.tfstate]
}

# Nadie de internet puede leerlo, aunque alguien se equivoque con los permisos
resource "aws_s3_bucket_public_access_block" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
