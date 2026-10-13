# Los "porteros" (security groups). Los creados con Terraform empiezan sin
# ninguna norma: ni de entrada ni de salida. Cada norma se añade aparte.

# ---------- Portero del balanceador ----------
resource "aws_security_group" "alb" {
  name        = "${local.name}-alb"
  description = "Load balancer: HTTP from the internet"
  vpc_id      = aws_vpc.main.id
}

# Entrada: cualquiera de internet, por la puerta 80 (HTTP)
resource "aws_vpc_security_group_ingress_rule" "alb_http_in" {
  security_group_id = aws_security_group.alb.id
  description       = "HTTP from anywhere"
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
  cidr_ipv4         = "0.0.0.0/0"
}

# Salida: solo hacia los contenedores del bot, por su puerta
resource "aws_vpc_security_group_egress_rule" "alb_to_app" {
  security_group_id            = aws_security_group.alb.id
  description                  = "Only to the app tasks"
  ip_protocol                  = "tcp"
  from_port                    = local.app_port
  to_port                      = local.app_port
  referenced_security_group_id = aws_security_group.app.id
}

# ---------- Portero del bot ----------
resource "aws_security_group" "app" {
  name        = "${local.name}-app"
  description = "App tasks: inbound only from the load balancer"
  vpc_id      = aws_vpc.main.id
}

# Entrada: SOLO quien lleve la "pulsera" del portero del balanceador
resource "aws_vpc_security_group_ingress_rule" "app_from_alb" {
  security_group_id            = aws_security_group.app.id
  description                  = "App port, only from the ALB"
  ip_protocol                  = "tcp"
  from_port                    = local.app_port
  to_port                      = local.app_port
  referenced_security_group_id = aws_security_group.alb.id
}

# Salida: solo HTTPS (puerta 443). Basta para Anthropic, Google, WhatsApp
# y los servicios de AWS (descargar la imagen de ECR, leer SSM, enviar logs)
resource "aws_vpc_security_group_egress_rule" "app_https_out" {
  security_group_id = aws_security_group.app.id
  description       = "HTTPS to the internet"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  cidr_ipv4         = "0.0.0.0/0"
}
