# -*- coding: utf-8 -*-
"""
Núcleo del agente: loop Claude <-> tools compartido por el canal de WhatsApp
(claude_agent.py) y el endpoint Custom LLM de VAPI (llm_service.py).
"""
import anthropic
from config import settings
from tools import TOOLS, dispatch_tool

# Sonnet 4.6: sobra para un bot de citas y cuesta ~3x menos que la gama Opus/Fable.
# No se pasa el parámetro `thinking`: para reservas no hace falta razonamiento
# extendido y así la latencia se mantiene baja.
MODEL = "claude-sonnet-4-6"

client = anthropic.Anthropic(api_key=settings.anthropic_api_key)


def run_agent_loop(system, messages: list[dict], effort: str = "medium", max_tokens: int = 1024) -> str:
    """Ejecuta el loop agentic (Claude -> tools -> resultados) y devuelve el texto final.

    `system` puede ser un string o una lista de bloques (para usar prompt caching).
    `effort` controla profundidad/coste: "low" para voz (latencia), "medium" para chat.
    """
    working_messages = list(messages)

    while True:
        response = client.messages.create(
            model=MODEL,
            max_tokens=max_tokens,
            system=system,
            tools=TOOLS,
            output_config={"effort": effort},
            messages=working_messages,
        )

        if response.stop_reason == "tool_use":
            working_messages.append({"role": "assistant", "content": response.content})

            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = dispatch_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

            working_messages.append({"role": "user", "content": tool_results})
            continue

        # end_turn, max_tokens, refusal... — devolver el texto que haya
        return extract_text(response)


def extract_text(response) -> str:
    for block in response.content:
        if block.type == "text":
            return block.text
    return "Lo siento, no pude procesar tu mensaje. Inténtalo de nuevo."
