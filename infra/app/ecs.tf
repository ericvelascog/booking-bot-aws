# El bot en marcha: cluster, ficha técnica (task definition) y encargado (service)

variable "image_tag" {
  description = "Etiqueta de la imagen en ECR (el commit del que salió)"
  type        = string
  # La que subimos a mano el 9-oct. En la Fase 3 la elegirá el pipeline.
  default = "f1f8886"
}

# El "micrófono": aquí acaba todo lo que el bot escribe (sus logs)
resource "aws_cloudwatch_log_group" "app" {
  name              = "/ecs/${local.name}"
  retention_in_days = 7
}

# El edificio. Con Fargate no hay servidores que gestionar: es gratis
resource "aws_ecs_cluster" "main" {
  name = local.name
}

# La ficha técnica: es el `docker run` del 6-oct, pero escrito para AWS
resource "aws_ecs_task_definition" "app" {
  family                   = local.name
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc" # cada tarea tiene su propia IP en la VPC
  cpu                      = 256      # 0,25 vCPU
  memory                   = 512      # 0,5 GB
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64" # la imagen se construyó en un PC x86
  }

  container_definitions = jsonencode([{
    name      = "app"
    image     = "${data.aws_ecr_repository.app.repository_url}:${var.image_tag}"
    essential = true

    portMappings = [{ containerPort = local.app_port, protocol = "tcp" }]

    # El equivalente a --env-file: ECS lee cada llave de SSM y se la da al
    # contenedor como variable de entorno. Para cada nombre de la lista,
    # una entrada { name, valueFrom }.
    secrets = [for name in local.secret_names : {
      name      = name
      valueFrom = "${local.ssm_prefix_arn}/${name}"
    }]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.app.name
        awslogs-region        = local.region
        awslogs-stream-prefix = "app"
      }
    }
  }])
}

# El encargado: mantiene 1 bot siempre encendido y lo apunta en el ALB
resource "aws_ecs_service" "app" {
  name            = local.name
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.app.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.public[*].id
    security_groups  = [aws_security_group.app.id]
    assign_public_ip = true # para salir a internet sin NAT (ADR-0001)
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.app.arn
    container_name   = "app"
    container_port   = local.app_port
  }

  # Al cambiar de versión: primero se enciende la nueva (hasta 200 %) y la
  # vieja no se apaga hasta que la nueva está sana (nunca menos del 100 %)
  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200

  # Interruptor de seguridad: si la versión nueva no arranca, volver a la anterior
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  # Margen al arrancar antes de que cuenten los chequeos de salud del ALB
  health_check_grace_period_seconds = 60

  # El listener del ALB tiene que existir antes de apuntar tareas en él
  depends_on = [aws_lb_listener.http]
}
