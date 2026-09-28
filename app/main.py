import asyncio
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import StreamingResponse
from config import settings
from claude_agent import process_message
from whatsapp_service import send_message
from vapi_service import process_vapi_request
from llm_service import (
    _openai_to_anthropic_messages,
    _run_agentic_loop,
    build_streaming_response,
    build_non_streaming_response,
)

app = FastAPI(title="WhatsApp Fisio Bot")


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


@app.post("/webhook")
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
        await send_message(
            phone,
            "Lo siento, ha ocurrido un error. Por favor, inténtalo de nuevo en unos momentos.",
        )
        print(f"Error procesando mensaje de {phone}: {e}")


@app.post("/llm/v1/chat/completions")
@app.post("/llm/chat/completions")
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


@app.post("/vapi")
async def vapi_webhook(request: Request):
    """Webhook único para todas las tool calls de VAPI."""
    body = await request.json()
    print(f"VAPI REQUEST: {body}")
    result = await asyncio.to_thread(process_vapi_request, body)
    print(f"VAPI RESPONSE: {result}")
    return result


@app.get("/health")
async def health():
    return {"status": "ok"}
