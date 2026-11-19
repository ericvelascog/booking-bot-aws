import asyncio
import logging
import os
from fastapi import Depends, FastAPI, Request, Response, HTTPException
from fastapi.responses import StreamingResponse
from config import settings
from claude_agent import process_message
from privacy import DropQueryString, mask_phone, summarize_vapi_request
from security import require_voice_api_key, require_whatsapp_signature
from whatsapp_service import send_message
from vapi_service import process_vapi_request
from llm_service import (
    _openai_to_anthropic_messages,
    _run_agentic_loop,
    build_streaming_response,
    build_non_streaming_response,
)

app = FastAPI(title="WhatsApp Fisio Bot")

# Los logs de acceso, sin lo que va después del "?" (privacy.py): ahí Meta manda
# el verify token. uvicorn configura sus logs antes de importar este archivo,
# así que el filtro se queda puesto
logging.getLogger("uvicorn.access").addFilter(DropQueryString())


@app.get("/webhook")
async def verify_webhook(request: Request):
    """Verificación inicial del webhook por parte de Meta."""
    params = request.query_params
    if (
        params.get("hub.mode") == "subscribe"
        and params.get("hub.verify_token") == settings.webhook_verify_token
    ):
        return Response(content=params.get("hub.challenge"), media_type="text/plain")
    raise HTTPException(status_code=403, detail="Verificación fallida")


# Solo mensajes firmados por Meta (security.py). Sin esto, cualquiera que
# conociera la URL podría hacerse pasar por WhatsApp y reservar o cancelar citas
@app.post("/webhook", dependencies=[Depends(require_whatsapp_signature)])
async def receive_message(request: Request):
    """Recibe mensajes de WhatsApp y responde usando el agente Claude."""
    body = await request.json()

    try:
        entry = body["entry"][0]
        changes = entry["changes"][0]
        value = changes["value"]

        # Ignorar eventos que no sean mensajes (ej: status updates)
        if "messages" not in value:
            return {"status": "ok"}

        message = value["messages"][0]
        phone = message["from"]
        msg_type = message.get("type", "")

        if msg_type != "text":
            await send_message(phone, "Por favor, envíame un mensaje de texto. 😊")
            return {"status": "ok"}

        user_text = message["text"]["body"]

        # Procesar en background para responder rápido a Meta (evita timeout)
        asyncio.create_task(_handle_message(phone, user_text))

    except (KeyError, IndexError):
        pass  # Payload inesperado — ignorar silenciosamente

    return {"status": "ok"}


async def _handle_message(phone: str, user_text: str) -> None:
    """Genera y envía la respuesta del bot."""
    try:
        response_text = await asyncio.to_thread(process_message, phone, user_text)
        await send_message(phone, response_text)
    except Exception as e:
        # PRIMERO el log, que es lo que cuenta la alarma message-errors: busca el
        # texto "Error procesando mensaje" (infra/app/alarms.tf), no cambiarlo.
        # Antes iba después de la disculpa, y si lo que fallaba era el envío por
        # WhatsApp, la disculpa también fallaba y el error no llegaba al log.
        # El teléfono va tapado (privacy.py)
        print(f"Error procesando mensaje de {mask_phone(phone)}: {e}")
        try:
            await send_message(
                phone,
                "Lo siento, ha ocurrido un error. Por favor, inténtalo de nuevo en unos momentos.",
            )
        except Exception as send_error:
            print(f"No se pudo enviar la disculpa a {mask_phone(phone)}: {send_error}")


# Las rutas de voz exigen la clave (security.py). Cada llamada gasta saldo de
# la API de Claude, así que no pueden quedar abiertas a cualquiera
voice_auth = [Depends(require_voice_api_key)]


@app.post("/llm/v1/chat/completions", dependencies=voice_auth)
@app.post("/llm/chat/completions", dependencies=voice_auth)
async def llm_chat_completions(request: Request):
    """Endpoint Custom LLM compatible con OpenAI para VAPI."""
    print(">>> VAPI LLM REQUEST RECIBIDO")
    body = await request.json()
    stream = body.get("stream", False)
    messages = body.get("messages", [])
    model = body.get("model", "claude-sonnet-4-6")

    system, anthropic_messages = _openai_to_anthropic_messages(messages)

    if not anthropic_messages:
        text = ""
    else:
        text = await asyncio.to_thread(_run_agentic_loop, system, anthropic_messages)

    if stream:
        return StreamingResponse(
            build_streaming_response(text, model),
            media_type="text/event-stream",
        )
    return build_non_streaming_response(text, model)


@app.post("/vapi", dependencies=voice_auth)
async def vapi_webhook(request: Request):
    """Webhook único para todas las tool calls de VAPI."""
    body = await request.json()
    # Solo un resumen (privacy.py). Antes se escribía el cuerpo entero, con el
    # nombre, el teléfono y la cita del paciente
    print(summarize_vapi_request(body))
    result = await asyncio.to_thread(process_vapi_request, body)
    print(f"VAPI response: {len(result.get('results', []))} results")
    return result


@app.get("/health")
async def health():
    # version = el commit del que se construyó la imagen (lo pone el pipeline)
    return {"status": "ok", "version": os.environ.get("APP_VERSION", "dev")}


@app.get("/")
async def root():
    return {"service": "booking-bot", "status": "ok", "health": "/health"}