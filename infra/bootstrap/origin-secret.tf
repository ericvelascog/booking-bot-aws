# La "contraseña" que CloudFront añade a cada petición (cabecera X-Origin-Verify)
# y que el ALB exige: así nadie puede llegar al ALB saltándose CloudFront.
#
# Vive en el bootstrap porque la necesitan dos capas, app (el ALB la comprueba)
# y edge (CloudFront la envía), y tiene que existir antes que ambas.
# Va fuera de /booking-bot/* para que el contenedor del bot no pueda leerla.
# Su valor queda en el estado de Terraform (bucket cifrado y privado): aceptable
# para un secreto cuyo único fin es comprobar el origen del tráfico.

resource "random_password" "origin_verify" {
  length  = 40
  special = false
}

resource "aws_ssm_parameter" "origin_verify" {
  name        = "/booking-bot-infra/origin-verify-secret"
  description = "Header value CloudFront sends and the ALB requires"
  type        = "SecureString"
  value       = random_password.origin_verify.result
}
