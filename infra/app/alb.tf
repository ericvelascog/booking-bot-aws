# El balanceador (ALB): la "recepción" que recibe las visitas de internet
# y se las pasa a los contenedores sanos

resource "aws_lb" "main" {
  name               = "${local.name}-alb"
  load_balancer_type = "application"
  internal           = false # de cara a internet
  security_groups    = [aws_security_group.alb.id]
  subnets            = aws_subnet.public[*].id

  # Tira las cabeceras HTTP con nombres no válidos antes de pasárselas al bot.
  # Defensa gratuita contra ataques de "request smuggling" (avisado por checkov)
  drop_invalid_header_fields = true

  # Avisos de checkov aceptados a propósito. Motivos: docs/security-scanning.md
  # checkov:skip=CKV_AWS_150:Ephemeral stack, destroyed after every session, so deletion protection would block terraform destroy
  # checkov:skip=CKV_AWS_91:Requests are already logged by the app in CloudWatch; ALB access logs are on the production list
  # checkov:skip=CKV2_AWS_20:No own domain, so no certificate for the ALB; HTTPS ends at CloudFront (ADR-0002)
  # checkov:skip=CKV2_AWS_28:WAF has a fixed monthly cost; the ALB only accepts CloudFront with the secret origin header
}

# La lista de "consultas": los contenedores que pueden atender y cómo se
# comprueba que están sanos. ECS apunta y borra los contenedores solo.
resource "aws_lb_target_group" "app" {
  name        = "${local.name}-app"
  port        = local.app_port
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip" # en Fargate cada contenedor se apunta por su IP

  health_check {
    path                = "/health"
    matcher             = "200"
    interval            = 30 # cada 30 s
    healthy_threshold   = 2  # 2 respuestas buenas seguidas = sano
    unhealthy_threshold = 3  # 3 fallos seguidos = enfermo
  }

  # Al apagar un contenedor, la recepción deja de mandarle visitas y le da
  # 30 s para terminar las que tiene (por defecto son 5 minutos)
  deregistration_delay = 30

  # checkov:skip=CKV_AWS_378:HTTP inside the VPC, from the ALB to the tasks; HTTPS ends at CloudFront (ADR-0002)
}

# La "contraseña" de CloudFront (creada en infra/bootstrap)
data "aws_ssm_parameter" "origin_verify" {
  name = "/booking-bot-infra/origin-verify-secret"
}

# El "oído": escucha en la puerta 80. Por defecto RECHAZA (403)...
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"

  # checkov:skip=CKV_AWS_2:No own domain, so no certificate for the ALB; viewers use HTTPS on CloudFront (ADR-0002)
  # checkov:skip=CKV_AWS_103:No TLS listener on the ALB, same reason as CKV_AWS_2

  default_action {
    type = "fixed-response"
    fixed_response {
      content_type = "text/plain"
      message_body = "Forbidden"
      status_code  = "403"
    }
  }
}

# ...y solo deja pasar al bot lo que trae la cabecera secreta de CloudFront
resource "aws_lb_listener_rule" "from_cloudfront" {
  listener_arn = aws_lb_listener.http.arn
  priority     = 1

  condition {
    http_header {
      http_header_name = "X-Origin-Verify"
      values           = [data.aws_ssm_parameter.origin_verify.value]
    }
  }

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.app.arn
  }
}
