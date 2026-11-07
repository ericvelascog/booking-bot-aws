# Capa "edge": CloudFront delante del ALB. Es PERMANENTE (no se destruye con
# infra/app), así que la URL https://xxxx.cloudfront.net no cambia nunca.
# No tiene coste fijo: solo se paga por tráfico, dentro del nivel gratuito.
#
# Orden al encender: primero infra/app (crea el ALB) y después infra/edge
# (apunta CloudFront al ALB nuevo). Por qué: docs/adr/0002-cloudfront-edge-stack.md

# Preguntas a AWS sobre lo que ya existe
data "aws_lb" "app" { # el ALB que crea infra/app
  name = "booking-bot-alb"
}

data "aws_ssm_parameter" "origin_verify" { # la "contraseña" creada en infra/bootstrap
  name = "/booking-bot-infra/origin-verify-secret"
}

# Políticas gestionadas por AWS: no guardar nada en caché (es una API, no una web
# estática) y reenviar al ALB todas las cabeceras, cookies y parámetros de la URL
# (el webhook de WhatsApp los necesita), salvo la cabecera Host
data "aws_cloudfront_cache_policy" "disabled" {
  name = "Managed-CachingDisabled"
}

data "aws_cloudfront_origin_request_policy" "all_viewer_except_host" {
  name = "Managed-AllViewerExceptHostHeader"
}

resource "aws_cloudfront_distribution" "app" {
  enabled         = true
  comment         = "booking-bot: HTTPS in front of the ALB"
  is_ipv6_enabled = true
  http_version    = "http2and3"
  price_class     = "PriceClass_100" # solo los puntos de Europa y Norteamérica: el más barato

  origin {
    origin_id   = "alb"
    domain_name = data.aws_lb.app.dns_name

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "http-only" # el ALB no tiene certificado (no hay dominio propio)
      origin_ssl_protocols   = ["TLSv1.2"]
      origin_read_timeout    = 60 # margen para respuestas largas de Claude
    }

    # La "contraseña" que el ALB exige en cada petición
    custom_header {
      name  = "X-Origin-Verify"
      value = data.aws_ssm_parameter.origin_verify.value
    }
  }

  default_cache_behavior {
    target_origin_id         = "alb"
    viewer_protocol_policy   = "redirect-to-https" # si alguien entra por http://, lo manda a https://
    allowed_methods          = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods           = ["GET", "HEAD"]
    cache_policy_id          = data.aws_cloudfront_cache_policy.disabled.id
    origin_request_policy_id = data.aws_cloudfront_origin_request_policy.all_viewer_except_host.id
    compress                 = true
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  # El certificado gratuito de *.cloudfront.net
  viewer_certificate {
    cloudfront_default_certificate = true
  }
}
