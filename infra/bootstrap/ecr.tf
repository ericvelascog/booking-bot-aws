# ECR: el almacén privado de imágenes de Docker. Fargate descarga de aquí la
# imagen del bot cada vez que arranca un contenedor.

resource "aws_ecr_repository" "app" {
  name = "booking-bot"

  # Una etiqueta (por ejemplo, el commit a1b2c3d) no se puede sobrescribir:
  # cada versión publicada es única y nadie puede colar otra con el mismo nombre
  image_tag_mutability = "IMMUTABLE"

  # AWS revisa cada imagen al subirla buscando vulnerabilidades conocidas
  image_scanning_configuration {
    scan_on_push = true
  }
}

# Guardar solo las 5 imágenes más recientes: las viejas se borran solas
# y no se paga almacenamiento por versiones que ya nadie usa
resource "aws_ecr_lifecycle_policy" "app" {
  repository = aws_ecr_repository.app.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep only the 5 most recent images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 5
      }
      action = { type = "expire" }
    }]
  })
}
