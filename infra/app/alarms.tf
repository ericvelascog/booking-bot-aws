# Alarmas: avisan por email (tema de SNS de infra/bootstrap) cuando algo va mal,
# y otra vez cuando se arregla. Qué hacer con cada una: docs/runbook.md

data "aws_sns_topic" "alerts" {
  name = "booking-bot-alerts"
}

locals {
  notify      = [data.aws_sns_topic.alerts.arn]
  runbook_url = "https://github.com/ericvelascog/booking-bot-aws/blob/main/docs/runbook.md"
}

# 1. El bot o el balanceador devuelven errores 5xx.
#    Suma dos métricas del ALB: los 5xx que genera nuestra app (Target) y los que
#    genera el propio ALB (ELB), por ejemplo un 503 cuando no queda ninguna tarea sana.
resource "aws_cloudwatch_metric_alarm" "http_5xx" {
  alarm_name          = "${local.name}-http-5xx"
  alarm_description   = "5 or more 5xx responses in 1 minute (from the app or from the ALB). Runbook: ${local.runbook_url}#http-5xx"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = 5
  evaluation_periods  = 1
  treat_missing_data  = "notBreaching" # sin tráfico no hay datos, y eso no es un error

  metric_query {
    id          = "total"
    expression  = "FILL(app, 0) + FILL(alb, 0)"
    label       = "5xx responses"
    return_data = true
  }

  metric_query {
    id = "app"
    metric {
      namespace   = "AWS/ApplicationELB"
      metric_name = "HTTPCode_Target_5XX_Count"
      dimensions  = { LoadBalancer = aws_lb.main.arn_suffix }
      period      = 60
      stat        = "Sum"
    }
  }

  metric_query {
    id = "alb"
    metric {
      namespace   = "AWS/ApplicationELB"
      metric_name = "HTTPCode_ELB_5XX_Count"
      dimensions  = { LoadBalancer = aws_lb.main.arn_suffix }
      period      = 60
      stat        = "Sum"
    }
  }

  alarm_actions = local.notify
  ok_actions    = local.notify
}

# 2. Alguna tarea suspende el health check del ALB durante 2 minutos seguidos
resource "aws_cloudwatch_metric_alarm" "unhealthy_targets" {
  alarm_name          = "${local.name}-unhealthy-targets"
  alarm_description   = "At least one task has failed the ALB health check for 2 minutes. Runbook: ${local.runbook_url}#unhealthy-targets"
  namespace           = "AWS/ApplicationELB"
  metric_name         = "UnHealthyHostCount"
  dimensions          = { LoadBalancer = aws_lb.main.arn_suffix, TargetGroup = aws_lb_target_group.app.arn_suffix }
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 2
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = 1
  treat_missing_data  = "notBreaching"

  alarm_actions = local.notify
  ok_actions    = local.notify
}

# 3. El bot no ha podido contestar un mensaje de WhatsApp.
#    Las alarmas de arriba no lo ven: el webhook responde 200 a Meta al momento y
#    procesa el mensaje después, así que un fallo (como la clave de Claude
#    revocada, troubleshooting #006) solo aparece en los logs. Este filtro cuenta
#    esas líneas de log y las convierte en una métrica.
resource "aws_cloudwatch_log_metric_filter" "message_errors" {
  name           = "${local.name}-message-errors"
  log_group_name = aws_cloudwatch_log_group.app.name
  pattern        = "\"Error procesando mensaje\"" # la línea que escribe main.py cuando falla

  metric_transformation {
    namespace = "BookingBot"
    name      = "MessageProcessingErrors"
    value     = "1" # cada línea que coincide suma 1
  }
}

resource "aws_cloudwatch_metric_alarm" "message_errors" {
  alarm_name          = "${local.name}-message-errors"
  alarm_description   = "The bot failed to answer a WhatsApp message (the webhook still returned 200, so the 5xx alarm does not see it). Runbook: ${local.runbook_url}#message-errors"
  namespace           = "BookingBot"
  metric_name         = "MessageProcessingErrors"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = 1
  treat_missing_data  = "notBreaching"

  alarm_actions = local.notify
  ok_actions    = local.notify

  # La métrica no existe hasta que el filtro la crea
  depends_on = [aws_cloudwatch_log_metric_filter.message_errors]
}
