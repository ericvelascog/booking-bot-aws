# GitHub Actions entra en AWS con OIDC: sin ninguna clave guardada en GitHub.
# GitHub firma una "tarjeta" (token) en cada ejecución; AWS la comprueba y, si
# viene de nuestro repo y de la rama main, da credenciales temporales (1 h).

locals {
  # GitHub identifica el repo en la tarjeta con nombres + IDs numéricos
  # ("immutable subject"): si alguien borrara el repo y creara otro con el
  # mismo nombre, tendría otro ID y AWS lo rechazaría. Se consulta con:
  #   gh api repos/ericvelascog/booking-bot-aws/actions/oidc/customization/sub
  github_subject_prefix = "repo:ericvelascog@234643949/booking-bot-aws@1397462375"
  account_id            = data.aws_caller_identity.current.account_id
}

data "aws_caller_identity" "current" {}

# 1. AWS confía en las tarjetas que firma GitHub (una vez por cuenta)
resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
}

# 2. Quién puede ponerse el rol: SOLO los workflows de nuestro repo en la rama main
data "aws_iam_policy_document" "github_assume" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["${local.github_subject_prefix}:ref:refs/heads/main"]
    }
  }
}

resource "aws_iam_role" "github_deploy" {
  name                 = "booking-bot-github-deploy"
  assume_role_policy   = data.aws_iam_policy_document.github_assume.json
  max_session_duration = 3600 # las credenciales caducan en 1 hora
}

# 3. Qué puede hacer: lo justo para publicar una imagen y desplegarla
data "aws_iam_policy_document" "github_deploy" {
  statement {
    sid       = "LogInToEcr"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"] # AWS no permite limitar esta acción a un almacén concreto
  }

  statement {
    sid = "PushImagesToOurRepository"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:InitiateLayerUpload",
      "ecr:UploadLayerPart",
      "ecr:CompleteLayerUpload",
      "ecr:PutImage",
      "ecr:BatchGetImage",
    ]
    resources = [aws_ecr_repository.app.arn]
  }

  statement {
    sid       = "RegisterTaskDefinitions"
    actions   = ["ecs:RegisterTaskDefinition", "ecs:DescribeTaskDefinition"]
    resources = ["*"] # estas dos acciones no admiten limitarse a un recurso
  }

  statement {
    sid       = "DeployOnlyOurService"
    actions   = ["ecs:UpdateService", "ecs:DescribeServices"]
    resources = ["arn:aws:ecs:eu-west-1:${local.account_id}:service/booking-bot/booking-bot"]
  }

  # Entregar a ECS las acreditaciones del bot, y SOLO esas dos: así nadie puede
  # registrar una ficha técnica con un rol más poderoso (escalada de privilegios)
  statement {
    sid     = "PassOnlyTheAppRoles"
    actions = ["iam:PassRole"]
    resources = [
      "arn:aws:iam::${local.account_id}:role/booking-bot-execution",
      "arn:aws:iam::${local.account_id}:role/booking-bot-task",
    ]
    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy" "github_deploy" {
  name   = "push-image-and-deploy"
  role   = aws_iam_role.github_deploy.id
  policy = data.aws_iam_policy_document.github_deploy.json
}

# ---------- Rol de SOLO LECTURA para `terraform plan` en los pull requests ----------
# El workflow de los PR (.github/workflows/plan.yml) lo usa para calcular qué
# cambiaría en AWS y publicarlo en el PR.
#
# Ojo: ese workflow se ejecuta en la versión de la RAMA del PR, así que quien
# pueda abrir un PR en este repo decide qué código usa este rol. Por eso el rol
# no puede cambiar nada, y tampoco puede leer secretos ni datos personales.
# (Los PR que vienen de forks no reciben tarjeta OIDC: GitHub no se la da.)

# 1. Quién puede ponerse el rol: SOLO los workflows de pull requests de nuestro repo
data "aws_iam_policy_document" "github_plan_assume" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["${local.github_subject_prefix}:pull_request"]
    }
  }
}

resource "aws_iam_role" "github_plan" {
  name                 = "booking-bot-github-plan"
  assume_role_policy   = data.aws_iam_policy_document.github_plan_assume.json
  max_session_duration = 3600 # las credenciales caducan en 1 hora
}

# 2. Qué puede hacer: LEER la configuración de todo (la política de AWS ReadOnlyAccess)...
resource "aws_iam_role_policy_attachment" "github_plan_read_only" {
  role       = aws_iam_role.github_plan.name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}

# 3. ...MENOS los datos. ReadOnlyAccess también deja leer CONTENIDO: los secretos
#    del bot en SSM, los logs (con números de teléfono), las conversaciones de la
#    tabla y las grabaciones de CloudTrail. Un Deny explícito gana siempre a
#    cualquier Allow. Nada de esto le hace falta a `terraform plan`.
#    Sí puede leer el secreto del origen (/booking-bot-infra/...) y el estado de
#    Terraform: el plan los necesita.
data "aws_iam_policy_document" "github_plan_deny_data" {
  statement {
    sid    = "NeverReadTheAppSecrets"
    effect = "Deny"
    actions = [
      "ssm:GetParameter",
      "ssm:GetParameters",
      "ssm:GetParametersByPath",
      "ssm:GetParameterHistory",
    ]
    resources = [
      "arn:aws:ssm:eu-west-1:${local.account_id}:parameter/booking-bot",
      "arn:aws:ssm:eu-west-1:${local.account_id}:parameter/booking-bot/*",
    ]
  }

  statement {
    sid    = "NeverReadLogs"
    effect = "Deny"
    actions = [
      "logs:GetLogEvents",
      "logs:FilterLogEvents",
      "logs:StartQuery",
      "logs:GetQueryResults",
      "logs:StartLiveTail",
      "logs:GetLogRecord",
      "logs:Unmask",
    ]
    resources = ["*"]
  }

  statement {
    sid    = "NeverReadConversations"
    effect = "Deny"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:BatchGetItem",
      "dynamodb:Query",
      "dynamodb:Scan",
      "dynamodb:PartiQLSelect",
    ]
    resources = ["*"]
  }

  # Solo los objetos del bucket de CloudTrail: el estado de Terraform, en el
  # otro bucket, sí tiene que poder leerlo
  statement {
    sid       = "NeverReadTheAuditLogFiles"
    effect    = "Deny"
    actions   = ["s3:GetObject", "s3:GetObjectVersion"]
    resources = ["${aws_s3_bucket.cloudtrail.arn}/*"]
  }

  statement {
    sid       = "NeverReadTheEventHistory"
    effect    = "Deny"
    actions   = ["cloudtrail:LookupEvents"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "github_plan_deny_data" {
  name   = "deny-reading-secrets-and-personal-data"
  role   = aws_iam_role.github_plan.id
  policy = data.aws_iam_policy_document.github_plan_deny_data.json
}
