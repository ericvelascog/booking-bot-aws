import json
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo
from agent_core import MODEL, run_agent_loop


def _inject_date(system_prompt: str) -> str:
    """Reemplaza {{now}} o inyecta la fecha actual si no está ya."""
    now = datetime.now(ZoneInfo("Europe/Madrid")).strftime("%A %d/%m/%Y %H:%M")
    if "{{now}}" in system_prompt:
        return system_prompt.replace("{{now}}", now)
    return system_prompt + f"\n\nFecha y hora actual: {now}"


def _openai_to_anthropic_messages(messages: list[dict]) -> tuple[str, list[dict]]:
    """
    Convierte mensajes OpenAI a formato Anthropic.
    Devuelve (system_prompt, messages_list).
    """
    system_prompt = ""
    anthropic_messages = []

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "") or ""

        if role == "system":
            system_prompt += content + "\n"
        elif role in ("user", "assistant"):
            anthropic_messages.append({"role": role, "content": content})

    return _inject_date(system_prompt.strip()), anthropic_messages


def _run_agentic_loop(system: str, messages: list[dict]) -> str:
    """Loop Claude + tools para el endpoint de voz.

    effort="low": en una llamada de voz la latencia manda; las reservas no
    necesitan razonamiento profundo. El bloque de system lleva cache_control:
    dentro de una misma llamada VAPI manda varias peticiones por minuto con el
    mismo prefijo, así que los turnos siguientes leen de caché.
    """
    system_blocks = [
        {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
    ]
    return run_agent_loop(system_blocks, messages, effort="low")


def build_streaming_response(text: str, model: str = MODEL):
    """
    Genera chunks SSE en formato OpenAI para enviar a VAPI.
    Emite el texto en un único chunk y cierra con [DONE].
    """
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created = int(datetime.now().timestamp())

    # Chunk con el contenido
    chunk = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{
            "index": 0,
            "delta": {"role": "assistant", "content": text},
            "finish_reason": None,
        }],
    }
    yield f"data: {json.dumps(chunk)}\n\n"

    # Chunk de cierre
    closing = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{
            "index": 0,
            "delta": {},
            "finish_reason": "stop",
        }],
    }
    yield f"data: {json.dumps(closing)}\n\n"
    yield "data: [DONE]\n\n"


def build_non_streaming_response(text: str, model: str = MODEL) -> dict:
    """Respuesta OpenAI estándar (no streaming)."""
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(datetime.now().timestamp()),
        "model": model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": text},
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }
