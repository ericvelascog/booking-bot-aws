# Los dos roles del contenedor del bot

locals {
  # Las 6 llaves que subió scripts/put-secrets.ps1 a SSM (/booking-bot/<NOMBRE>)
  secret_names = [
    "WHATSAPP_TOKEN",
    "WHATSAPP_PHONE_NUMBER_ID",
    "WEBHOOK_VERIFY_TOKEN",
    "ANTHROPIC_API_KEY",
    "GOOGLE_CALENDAR_ID",
    "GOOGLE_CREDENTIALS_CONTENT",
  ]
  ssm_prefix_arn = "arn:aws:ssm:${local.region}:${data.aws_caller_identity.current.account_id}:parameter/booking-bot"
}

# Política de confianza (quién puede "ponerse" estos roles): solo las tareas de ECS
data "aws_iam_policy_document" "ecs_tasks_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

# ---------- Execution role: el personal que prepara la consulta ----------
# Lo usa ECS (no nuestro código) para montar el contenedor
resource "aws_iam_role" "execution" {
  name               = "${local.name}-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

data "aws_iam_policy_document" "execution" {
  statement {
    sid       = "PullImageFromOurRepository"
    actions   = ["ecr:BatchCheckLayerAvailability", "ecr:GetDownloadUrlForLayer", "ecr:BatchGetImage"]
    resources = [data.aws_ecr_repository.app.arn]
  }

  statement {
    sid       = "LogInToEcr"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"] # AWS no permite limitar esta acción a un almacén concreto
  }

  statement {
    sid       = "WriteLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.app.arn}:*"]
  }

  statement {
    sid       = "ReadOnlyOurSecrets"
    actions   = ["ssm:GetParameters"]
    resources = ["${local.ssm_prefix_arn}/*"]
  }
}

resource "aws_iam_role_policy" "execution" {
  name   = "pull-image-write-logs-read-secrets"
  role   = aws_iam_role.execution.id
  policy = data.aws_iam_policy_document.execution.json
}

# ---------- Task role: la acreditación de nuestro código ----------
# Sin permisos: la app no llama a ninguna API de AWS.
# (En la v1, con las sesiones en DynamoDB, tendrá permiso solo para su tabla.)
resource "aws_iam_role" "task" {
  name               = "${local.name}-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}
