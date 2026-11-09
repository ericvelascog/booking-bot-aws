"""Conversaciones de WhatsApp: los últimos mensajes de cada número.

Dos implementaciones con las mismas tres funciones, y se elige una al arrancar:

- DynamoDB, si existe la variable SESSIONS_TABLE (en AWS la pone Terraform).
  Todas las tareas comparten la tabla, así que da igual cuál atienda cada
  mensaje, y reiniciar o sustituir una tarea no borra ninguna conversación.
- La memoria del proceso, si no existe (en local y en los tests). Es lo que
  había antes: se pierde al reiniciar y no se comparte entre tareas.

El resto del bot solo usa get_history, add_message y clear_session, así que
no sabe (ni le importa) dónde se guarda la conversación.
"""
import os
import time

import boto3

MAX_MESSAGES = 20

# Tras este tiempo sin actividad la conversación empieza de cero: evita que un
# paciente que escribe días después arrastre el contexto (y los tokens) de la
# conversación anterior, y no guarda datos personales más de lo necesario.
SESSION_TTL_SECONDS = 6 * 60 * 60


def _now() -> float:
    return time.time()


def _new_expiry() -> int:
    return int(_now()) + SESSION_TTL_SECONDS


def _is_expired(expires_at) -> bool:
    # int(): DynamoDB devuelve los números como Decimal
    return int(expires_at) <= _now()


class MemorySessionStore:
    """Un diccionario en la memoria del proceso: {phone: {messages, expires_at}}."""

    def __init__(self):
        self._sessions: dict[str, dict] = {}

    def get_history(self, phone: str) -> list[dict]:
        session = self._sessions.get(phone)
        if session is None or _is_expired(session["expires_at"]):
            return []
        return list(session["messages"])

    def add_message(self, phone: str, role: str, content) -> None:
        messages = self.get_history(phone) + [{"role": role, "content": content}]
        self._sessions[phone] = {
            "messages": messages[-MAX_MESSAGES:],  # solo los últimos, para controlar tokens
            "expires_at": _new_expiry(),
        }

    def clear_session(self, phone: str) -> None:
        self._sessions.pop(phone, None)


class DynamoSessionStore:
    """Una ficha por número en DynamoDB: {phone, messages, expires_at}.

    `expires_at` es el atributo TTL de la tabla: DynamoDB borra la ficha sola
    cuando pasa esa hora (en segundos desde 1970).
    """

    def __init__(self, table):
        self._table = table  # una tabla de boto3: boto3.resource("dynamodb").Table(...)

    def get_history(self, phone: str) -> list[dict]:
        # ConsistentRead: devuelve siempre la última versión, aunque la haya
        # escrito otra tarea hace milisegundos. Sin él, DynamoDB podría
        # devolver la anterior (lectura "eventualmente consistente").
        item = self._table.get_item(Key={"phone": phone}, ConsistentRead=True).get("Item")

        # El TTL de DynamoDB borra con retraso (puede tardar hasta un par de
        # días), así que la caducidad también se comprueba al leer.
        if item is None or _is_expired(item["expires_at"]):
            return []
        return item["messages"]

    def add_message(self, phone: str, role: str, content) -> None:
        messages = self.get_history(phone) + [{"role": role, "content": content}]
        self._table.put_item(
            Item={
                "phone": phone,
                "messages": messages[-MAX_MESSAGES:],
                "expires_at": _new_expiry(),
            }
        )

    def clear_session(self, phone: str) -> None:
        self._table.delete_item(Key={"phone": phone})


def _build_store():
    table_name = os.environ.get("SESSIONS_TABLE")
    if not table_name:
        return MemorySessionStore()

    # Sin claves en el código: dentro de ECS, boto3 obtiene solo las
    # credenciales temporales del task role
    dynamodb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "eu-west-1"))
    return DynamoSessionStore(dynamodb.Table(table_name))


_store = _build_store()


def get_history(phone: str) -> list[dict]:
    return _store.get_history(phone)


def add_message(phone: str, role: str, content) -> None:
    _store.add_message(phone, role, content)


def clear_session(phone: str) -> None:
    _store.clear_session(phone)
