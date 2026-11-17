"""Comprobaciones de seguridad de las peticiones que llegan al bot."""
import hmac

from fastapi import HTTPException, Request

from config import settings


def require_voice_api_key(request: Request) -> None:
    """Deja pasar solo a quien envía la clave del canal de voz (/llm y /vapi).

    Acepta la clave en dos cabeceras:
    - `Authorization: Bearer <clave>`: la que envían los clientes compatibles
      con OpenAI y la credencial "Bearer Token" de Vapi.
    - `X-Vapi-Secret: <clave>`: el formato antiguo de Vapi.

    Se usa como dependencia de FastAPI, así que se ejecuta ANTES que la ruta:
    sin clave, la petición se rechaza sin leer el cuerpo ni llamar a Claude.
    """
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer":
        token = request.headers.get("x-vapi-secret", "")
    token = token.strip()

    # compare_digest tarda lo mismo acierte o falle. Con un == normal, una clave
    # que empieza bien tarda un poco más en fallar, y midiendo ese tiempo se
    # podría adivinar letra a letra. Compara bytes: con texto, un carácter
    # no ASCII daría un error 500 en vez de un 401.
    if not token or not hmac.compare_digest(token.encode(), settings.voice_api_key.encode()):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
