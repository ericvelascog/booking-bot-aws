# GitHub Actions entra en AWS con OIDC: sin ninguna clave guardada en GitHub.
# GitHub firma una "tarjeta" (token) en cada ejecución; AWS la comprueba y, si
# viene de nuestro repo y de la rama main, da credenciales temporales (1 h).

locals {
  github_repo = "ericvelascog/booking-bot-aws"
  account_id  = data.aws_caller_identity.current.account_id
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
      values   = ["repo:${local.github_repo}:ref:refs/heads/main"]
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

  statement {
    sid       = "FindTheLoadBalancerForTheSmokeTest"
    actions   = ["elasticloadbalancing:DescribeLoadBalancers"]
    resources = ["*"] # acción de solo lectura que no admite limitarse a un recurso
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
