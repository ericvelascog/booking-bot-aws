"""Los logs no llevan teléfonos completos ni datos de los pacientes."""
import asyncio
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import main
from config import settings
from main import app
from privacy import mask_phone, summarize_vapi_request

client = TestClient(app)

PHONE = "34600112233"  # inventado
ALARMS_TF = Path(__file__).resolve().parents[2] / "infra" / "app" / "alarms.tf"


@pytest.mark.parametrize("phone, masked", [
    ("34600112233", "********233"),
    ("600112233", "******233"),
    ("123", "***"),
    ("", "***"),
])
def test_mask_phone_keeps_only_the_last_three_digits(phone, masked):
    assert mask_phone(phone) == masked


def failing_message_log(monkeypatch, capsys) -> str:
    """Hace fallar el procesamiento de un mensaje y devuelve lo que se escribe en el log."""
    def broken_agent(phone, text):
        raise RuntimeError("Anthropic API returned 401")

    async def fake_send(phone, text):
        pass

    monkeypatch.setattr(main, "process_message", broken_agent)
    monkeypatch.setattr(main, "send_message", fake_send)
    asyncio.run(main._handle_message(PHONE, "Hola"))
    return capsys.readouterr().out


def test_the_error_log_masks_the_phone_but_keeps_the_cause(monkeypatch, capsys):
    out = failing_message_log(monkeypatch, capsys)

    assert PHONE not in out
    assert "********233" in out
    assert "Anthropic API returned 401" in out  # el motivo del fallo sigue ahí para diagnosticar


def test_the_error_log_still_triggers_the_alarm(monkeypatch, capsys):
    # La alarma message-errors cuenta las líneas que contienen el texto de su filtro.
    # Si alguien cambia el mensaje del log, la alarma dejaría de saltar sin avisar
    if not ALARMS_TF.exists():
        pytest.skip("infra/ is not available (tests run with only app/ mounted)")
    pattern =re.search(r'pattern\s*=\s*"\\"(.+?)\\""', ALARMS_TF.read_text(encoding="utf-8")).group(1)

    out = failing_message_log(monkeypatch, capsys)

    assert pattern in out


def test_a_failure_sending_on_whatsapp_is_still_logged(monkeypatch, capsys):
    # Si lo que falla es WhatsApp (p. ej. un token caducado), la disculpa tampoco
    # se puede enviar. El error tiene que llegar al log igualmente, o la alarma no salta
    async def broken_whatsapp(phone, text):
        raise RuntimeError("WhatsApp API returned 401")

    monkeypatch.setattr(main, "process_message", lambda phone, text: "Tenemos hueco el jueves")
    monkeypatch.setattr(main, "send_message", broken_whatsapp)

    asyncio.run(main._handle_message(PHONE, "Hola"))  # no lanza la excepción hacia fuera
    out = capsys.readouterr().out

    assert "Error procesando mensaje de ********233: WhatsApp API returned 401" in out
    assert "No se pudo enviar la disculpa a ********233" in out
    assert PHONE not in out


VAPI_BOOKING = {
    "message": {
        "type": "tool-calls",
        "toolCallList": [{
            "id": "call-1",
            "function": {
                "name": "bookAppointment",
                "arguments": {"name": "Ana García", "phone": PHONE, "date": "2026-11-20", "time": "17:00"},
            },
        }],
    },
}


def test_the_vapi_log_has_no_patient_data(monkeypatch, capsys):
    monkeypatch.setattr(main, "process_vapi_request", lambda body: {
        "results": [{"toolCallId": "call-1", "result": "Cita reservada para Ana García el jueves a las 17:00"}],
    })

    response = client.post("/vapi", json=VAPI_BOOKING, headers={"X-Vapi-Secret": settings.voice_api_key})
    out = capsys.readouterr().out

    assert response.status_code == 200
    assert "bookAppointment" in out  # se sabe qué se pidió...
    assert "Ana" not in out and PHONE not in out and "17:00" not in out  # ...pero no de quién


@pytest.mark.parametrize("body", [None, "texto", [], {"message": "texto"}, {"message": {"toolCallList": ["x"]}}])
def test_the_vapi_summary_never_fails(body):
    assert summarize_vapi_request(body).startswith("VAPI request:")
