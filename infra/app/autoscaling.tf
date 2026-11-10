# Autoescalado: entre 2 y 4 tareas según cuántas peticiones recibe cada una.
#
# Por qué peticiones y no CPU: el bot pasa casi todo el tiempo ESPERANDO
# (a Claude, a Google Calendar, a WhatsApp), no calculando. Con mucho tráfico
# las tareas se saturan de peticiones abiertas mientras la CPU sigue baja, así
# que una regla por CPU reaccionaría tarde o nunca.

# Qué se escala y entre qué límites
resource "aws_appautoscaling_target" "app" {
  service_namespace  = "ecs"
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.app.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  min_capacity       = 2 # nunca menos de una por zona
  max_capacity       = 4 # techo de gasto: como mucho, el doble de lo normal
}

# La regla: "target tracking", como un termostato. Se le da un objetivo y AWS
# añade o quita tareas para mantenerse cerca. Crea por su cuenta las dos
# alarmas de CloudWatch que necesita (subir y bajar).
resource "aws_appautoscaling_policy" "requests" {
  name               = "${local.name}-requests-per-task"
  policy_type        = "TargetTrackingScaling"
  service_namespace  = aws_appautoscaling_target.app.service_namespace
  resource_id        = aws_appautoscaling_target.app.resource_id
  scalable_dimension = aws_appautoscaling_target.app.scalable_dimension

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ALBRequestCountPerTarget"
      # Qué ALB y qué grupo de destino mirar
      resource_label = "${aws_lb.main.arn_suffix}/${aws_lb_target_group.app.arn_suffix}"
    }

    target_value       = 120 # peticiones por tarea y por minuto
    scale_out_cooldown = 60  # tras añadir una tarea, esperar 1 min antes de añadir otra
    scale_in_cooldown  = 300 # para quitar tareas, sin prisa: 5 min
  }
}
