"""Comprobaciones de seguridad de las peticiones que llegan al bot."""
import hashlib
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


async def require_whatsapp_signature(request: Request) -> None:
    """Deja pasar solo los mensajes que ha firmado Meta (cabecera X-Hub-Signature-256).

    Meta calcula un HMAC-SHA256 del cuerpo de la petición con el App Secret, un
    secreto que solo conocemos Meta y nosotros, y lo envía como
    "sha256=<64 caracteres hexadecimales>". Aquí se repite el cálculo con nuestra
    copia del secreto: si sale lo mismo, el mensaje viene de Meta (autenticidad)
    y nadie lo ha cambiado por el camino (integridad).

    Se firma el cuerpo EXACTO, byte a byte, tal como llegó. Si se convirtiera a
    JSON y otra vez a texto, cambiarían los espacios o los acentos y la firma ya
    no cuadraría. FastAPI guarda el cuerpo leído, así que la ruta puede volver
    a leerlo después.
    """
    body = await request.body()
    expected = "sha256=" + hmac.new(
        settings.whatsapp_app_secret.encode(), body, hashlib.sha256
    ).hexdigest()
    received = request.headers.get("x-hub-signature-256", "")

    # compare_digest, igual que con la clave de voz: tarda lo mismo acierte o falle
    if not hmac.compare_digest(received.encode(), expected.encode()):
        # Sin datos de la petición: solo que se ha rechazado, para poder buscarlo
        print("Webhook rechazado: firma X-Hub-Signature-256 ausente o incorrecta")
        raise HTTPException(status_code=403, detail="Invalid signature")
