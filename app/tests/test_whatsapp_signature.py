"""La firma de Meta en /webhook (X-Hub-Signature-256): sin firma buena, no se procesa nada."""
import asyncio
import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import main
from config import Settings, settings
from main import app

client = TestClient(app)

# Un mensaje de texto como los que manda Meta (número y nombre inventados).
# Con acentos y "¿": se firma el cuerpo tal cual, en bytes UTF-8
MESSAGE = json.dumps({
    "entry": [{"changes": [{"value": {"messages": [{
        "from": "34600000000",
        "type": "text",
        "text": {"body": "Hola, ¿tenéis cita el jueves?"},
    }]}}]}],
}, ensure_ascii=False).encode("utf-8")


def sign(body: bytes, secret: str = settings.whatsapp_app_secret) -> str:
    """Lo mismo que hace Meta: HMAC-SHA256 del cuerpo con el App Secret."""
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def post_webhook(body: bytes, signature=None):
    headers = {"Content-Type": "application/json"}
    if signature is not None:
        headers["X-Hub-Signature-256"] = signature
    return client.post("/webhook", content=body, headers=headers)


@pytest.fixture
def handled(monkeypatch):
    """Apunta los mensajes que llegan a procesarse, sin llamar a Claude ni a WhatsApp."""
    calls = []

    def fake_handle(phone, text):
        calls.append((phone, text))
        return asyncio.sleep(0)

    monkeypatch.setattr(main, "_handle_message", fake_handle)
    return calls


def test_a_message_signed_by_meta_is_processed(handled):
    response = post_webhook(MESSAGE, sign(MESSAGE))

    assert response.status_code == 200
    assert handled == [("34600000000", "Hola, ¿tenéis cita el jueves?")]


@pytest.mark.parametrize("signature", [
    None,  # sin cabecera
    "",  # cabecera vacía
    sign(MESSAGE, secret="otro-secreto-que-no-es-el-de-meta"),  # firmado por otro
    sign(MESSAGE).removeprefix("sha256="),  # la firma buena, pero sin "sha256="
    sign(MESSAGE).upper(),  # la firma buena, pero en mayúsculas
    "sha256=" + "0" * 64,  # forma correcta, valor inventado
])
def test_a_message_without_a_valid_signature_is_rejected(signature, handled):
    response = post_webhook(MESSAGE, signature)

    assert response.status_code == 403
    assert handled == []


def test_a_message_changed_after_signing_is_rejected(handled):
    # Alguien intercepta un mensaje firmado y cambia el texto: la firma ya no cuadra
    tampered = MESSAGE.replace("jueves".encode(), "viernes".encode())

    response = post_webhook(tampered, sign(MESSAGE))

    assert response.status_code == 403
    assert handled == []


def test_a_non_ascii_signature_is_rejected_without_an_error(handled):
    response = client.post(
        "/webhook",
        content=MESSAGE,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": "sha256=ñ".encode("latin-1")},
    )

    assert response.status_code == 403
    assert handled == []


def test_meta_webhook_verification_still_works_without_a_signature():
    # El GET con el que Meta da de alta el webhook no va firmado
    response = client.get("/webhook", params={
        "hub.mode": "subscribe",
        "hub.verify_token": settings.webhook_verify_token,
        "hub.challenge": "12345",
    })

    assert response.status_code == 200


def test_the_bot_refuses_to_start_with_a_truncated_app_secret(monkeypatch):
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "0123456789abcdef")  # 16 caracteres: copiado a medias

    with pytest.raises(ValidationError):
        Settings()
