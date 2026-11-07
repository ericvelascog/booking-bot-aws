# El balanceador (ALB): la "recepción" que recibe las visitas de internet
# y se las pasa a los contenedores sanos

resource "aws_lb" "main" {
  name               = "${local.name}-alb"
  load_balancer_type = "application"
  internal           = false # de cara a internet
  security_groups    = [aws_security_group.alb.id]
  subnets            = aws_subnet.public[*].id
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
