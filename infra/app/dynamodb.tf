# La "libreta compartida": las conversaciones de WhatsApp viven aquí y no en la
# memoria del contenedor. Así cualquier tarea puede atender cualquier mensaje, y
# reiniciar o sustituir una tarea no borra ninguna conversación.

resource "aws_dynamodb_table" "sessions" {
  name         = "${local.name}-sessions"
  billing_mode = "PAY_PER_REQUEST" # on-demand: sin capacidad reservada, se paga por petición
  hash_key     = "phone"           # la clave: el número de quien escribe

  # Solo se declaran los atributos que forman la clave. El resto (los mensajes y
  # la caducidad) se guardan sin declararlos: DynamoDB no tiene esquema fijo.
  attribute {
    name = "phone"
    type = "S" # String
  }

  # DynamoDB borra sola cada conversación cuando pasa la hora de expires_at
  # (6 h sin actividad). Así no guardamos datos personales más de lo necesario.
  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  # Sin copias de seguridad (point-in-time recovery): son datos que caducan en
  # 6 horas y la tabla vive en el stack que se destruye en cada sesión.
  # El cifrado en reposo está siempre activado en DynamoDB, con una clave de AWS.
}
