# El "megáfono" de las alarmas: un tema de SNS que reenvía cada aviso por email.
#
# Vive aquí (permanente) y no en infra/app: AWS exige confirmar la suscripción
# de email con un clic. Si el tema se creara y destruyera en cada sesión, habría
# que confirmarla cada vez. Aquí se confirma una sola vez.

variable "alert_email" {
  description = "Email que recibe las alarmas. Va en terraform.tfvars, que git ignora: el repo es público"
  type        = string
}

resource "aws_sns_topic" "alerts" {
  name = "booking-bot-alerts"

  # Sin cifrado KMS, a propósito: CloudWatch no puede publicar en un tema cifrado
  # con la clave gestionada por AWS (aws/sns) y las alarmas fallarían en silencio.
  # Haría falta una clave propia (1 $/mes), y los avisos no llevan datos sensibles.
}

resource "aws_sns_topic_subscription" "alerts_email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}
