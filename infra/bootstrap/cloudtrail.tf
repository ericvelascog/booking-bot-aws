# CloudTrail: la "cámara de seguridad" de la cuenta. Apunta cada llamada a la API
# de AWS (quién, qué, cuándo, desde dónde): crear o borrar recursos, cambiar
# permisos, iniciar sesión, asumir un rol...
#
# Sin trail, AWS solo guarda 90 días de eventos de gestión en la consola. El trail
# los copia a un bucket propio, de todas las regiones, durante 1 año y con una
# firma que permite demostrar que nadie los ha tocado.
#
# Vive en el bootstrap (permanente): la cámara tiene que grabar siempre, también
# cuando infra/app está apagada. Coste: el primer trail de la cuenta no paga los
# eventos de gestión; solo el almacenamiento en S3, céntimos al mes.

locals {
  trail_name = "booking-bot-trail"
  # El ARN se escribe a mano porque el bucket necesita conocerlo antes de que
  # exista el trail (el trail, a su vez, necesita que el bucket ya le deje escribir)
  trail_arn = "arn:aws:cloudtrail:eu-west-1:${local.account_id}:trail/${local.trail_name}"
}

# ---------- El bucket donde se guardan las grabaciones ----------

resource "aws_s3_bucket" "cloudtrail" {
  bucket = "ericvelascog-booking-bot-cloudtrail"

  # Sin force_destroy: Terraform no puede borrar el bucket mientras tenga logs.
  # Así nadie borra las grabaciones con un simple terraform destroy.

  # checkov:skip=CKV_AWS_145:Encrypted with SSE-S3 (AES-256); a customer managed KMS key costs 1 USD per month
  # checkov:skip=CKV_AWS_144:A replica in another region doubles the cost for a demo; versioning protects the logs from deletion
  # checkov:skip=CKV_AWS_18:Logging access to the log bucket would need yet another bucket; only CloudTrail writes here
  # checkov:skip=CKV2_AWS_62:Nothing needs to react to each new log file
}

resource "aws_s3_bucket_public_access_block" "cloudtrail" {
  bucket = aws_s3_bucket.cloudtrail.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "cloudtrail" {
  bucket = aws_s3_bucket.cloudtrail.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Versionado: si alguien borra o sobrescribe un log, la versión anterior se conserva
resource "aws_s3_bucket_versioning" "cloudtrail" {
  bucket = aws_s3_bucket.cloudtrail.id

  versioning_configuration {
    status = "Enabled"
  }
}

# Los logs se guardan 1 año y después se borran solos
resource "aws_s3_bucket_lifecycle_configuration" "cloudtrail" {
  bucket = aws_s3_bucket.cloudtrail.id

  rule {
    id     = "keep-logs-one-year"
    status = "Enabled"
    filter {} # todo el bucket

    expiration {
      days = 365
    }

    # Las versiones antiguas (de algo borrado o sobrescrito), 30 días más
    noncurrent_version_expiration {
      noncurrent_days = 30
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }

  depends_on = [aws_s3_bucket_versioning.cloudtrail]
}

# Quién puede escribir aquí: SOLO nuestro trail, y solo dentro de la carpeta de
# esta cuenta. Y nadie puede conectarse sin cifrar (HTTP en vez de HTTPS).
data "aws_iam_policy_document" "cloudtrail_bucket" {
  statement {
    sid       = "CloudTrailChecksTheBucket"
    actions   = ["s3:GetBucketAcl"]
    resources = [aws_s3_bucket.cloudtrail.arn]

    principals {
      type        = "Service"
      identifiers = ["cloudtrail.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceArn"
      values   = [local.trail_arn]
    }
  }

  statement {
    sid       = "OnlyOurTrailWritesLogs"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.cloudtrail.arn}/AWSLogs/${local.account_id}/*"]

    principals {
      type        = "Service"
      identifiers = ["cloudtrail.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "s3:x-amz-acl"
      values   = ["bucket-owner-full-control"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceArn"
      values   = [local.trail_arn]
    }
  }

  statement {
    sid       = "DenyUnencryptedConnections"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.cloudtrail.arn, "${aws_s3_bucket.cloudtrail.arn}/*"]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "cloudtrail" {
  bucket = aws_s3_bucket.cloudtrail.id
  policy = data.aws_iam_policy_document.cloudtrail_bucket.json

  # Dos cambios a la vez en el mismo bucket pueden chocar (OperationAborted):
  # primero el bloqueo de acceso público, después la política
  depends_on = [aws_s3_bucket_public_access_block.cloudtrail]
}

# ---------- La cámara ----------

resource "aws_cloudtrail" "main" {
  name           = local.trail_name
  s3_bucket_name = aws_s3_bucket.cloudtrail.id

  is_multi_region_trail         = true # graba en todas las regiones, no solo en Irlanda
  include_global_service_events = true # IAM, STS, CloudFront: servicios "globales"
  enable_log_file_validation    = true # firma cada hora los logs: se puede demostrar que nadie los ha tocado

  # 1. Todos los eventos de gestión: crear, cambiar o borrar recursos, permisos, logins...
  advanced_event_selector {
    name = "All management events"

    field_selector {
      field  = "eventCategory"
      equals = ["Management"]
    }
  }

  # 2. Quién lee o escribe el estado de Terraform. Es el archivo más delicado de
  #    la cuenta: describe toda la infraestructura y contiene el secreto del origen.
  #    Son eventos "de datos" (dentro de un bucket), que no se graban por defecto.
  #    Cuestan 0,10 $ por cada 100.000, y Terraform hace unos pocos por comando.
  advanced_event_selector {
    name = "Terraform state reads and writes"

    field_selector {
      field  = "eventCategory"
      equals = ["Data"]
    }

    field_selector {
      field  = "resources.type"
      equals = ["AWS::S3::Object"]
    }

    field_selector {
      field       = "resources.ARN"
      starts_with = ["${aws_s3_bucket.tfstate.arn}/"]
    }
  }

  # El bucket tiene que dejar escribir al trail antes de que el trail arranque
  depends_on = [aws_s3_bucket_policy.cloudtrail]

  # checkov:skip=CKV_AWS_35:Log files are encrypted with SSE-S3; a customer managed KMS key costs 1 USD per month
  # checkov:skip=CKV_AWS_252:No need for a notification for every log file delivered
  # checkov:skip=CKV2_AWS_10:Sending the trail to CloudWatch Logs costs per GB; alarms on events such as root logins are on the production list
}
