"""Protección de datos en los logs (RGPD: minimización de datos).

Los logs los pueden leer más personas y herramientas que la base de datos, y se
guardan aparte. Por eso no llevan teléfonos completos ni el contenido de las
conversaciones: solo lo necesario para diagnosticar un fallo.
"""
import logging


class DropQueryString(logging.Filter):
    """Quita de los logs de acceso de uvicorn lo que va después del "?" en la URL.

    Ahí pueden ir tokens y datos: por ejemplo, Meta manda el verify token en
    GET /webhook?hub.verify_token=...  El log se queda con el método, la ruta y
    el código de respuesta, que es lo que sirve para diagnosticar.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        # uvicorn escribe: '%s - "%s %s HTTP/%s" %d' con (cliente, método, ruta, versión, código)
        if isinstance(record.args, tuple) and len(record.args) == 5:
            client, method, path, version, status = record.args
            record.args = (client, method, str(path).split("?", 1)[0], version, status)
        return True  # la línea se escribe siempre, solo sin la query


def mask_phone(phone: str) -> str:
    """Deja solo las 3 últimas cifras: '34600112233' -> '********233'.

    Con 3 cifras se pueden relacionar las líneas de un mismo usuario en un fallo
    sin saber de quién es el número (como las tarjetas, que enseñan las 4 últimas).
    """
    phone = str(phone)
    if len(phone) <= 3:
        return "***"
    return "*" * (len(phone) - 3) + phone[-3:]


def summarize_vapi_request(body) -> str:
    """Resume una petición de Vapi para el log: el tipo de evento y qué herramientas pide.

    Nunca los argumentos: ahí van el nombre, el teléfono y la cita del paciente.
    Si la petición no tiene la forma esperada, no falla: el resumen solo es para el log.
    """
    try:
        message = body.get("message") or {}
        names = [call["function"]["name"] for call in message.get("toolCallList") or []]
        return f"VAPI request: type={message.get('type', '?')} tools={names}"
    except (AttributeError, KeyError, TypeError):
        return "VAPI request: unexpected format"
