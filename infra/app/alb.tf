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

# El "oído": escucha en la puerta 80 y lo manda todo al target group
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.app.arn
  }
}
