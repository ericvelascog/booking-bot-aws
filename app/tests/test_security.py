"""La clave de las rutas de voz (/llm y /vapi): sin ella no se hace nada."""
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import main
from config import Settings, settings
from main import app

client = TestClient(app)

VOICE_ROUTES = ["/llm/chat/completions", "/llm/v1/chat/completions", "/vapi"]


@pytest.fixture
def no_work_allowed(monkeypatch):
    """Si una petición rechazada llegara a llamar a Claude o a VAPI, el test falla."""
    def fail(*args, **kwargs):
        raise AssertionError("a request without a valid key reached the bot")

    monkeypatch.setattr(main, "_run_agentic_loop", fail)
    monkeypatch.setattr(main, "process_vapi_request", fail)


@pytest.mark.parametrize("path", VOICE_ROUTES)
def test_voice_routes_reject_requests_without_a_key(path, no_work_allowed):
    response = client.post(path, json={"messages": [{"role": "user", "content": "hola"}]})

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("headers", [
    {"Authorization": "Bearer clave-falsa"},
    {"X-Vapi-Secret": "clave-falsa"},
    {"Authorization": f"Basic {settings.voice_api_key}"},  # la clave buena, pero sin "Bearer"
    # Caracteres no ASCII, en bytes como los mandaría un cliente cualquiera: 401, no un error 500
    {"Authorization": "Bearer ñandú".encode("latin-1")},
])
@pytest.mark.parametrize("path", VOICE_ROUTES)
def test_voice_routes_reject_a_wrong_key(path, headers, no_work_allowed):
    response = client.post(path, json={"messages": [{"role": "user", "content": "hola"}]}, headers=headers)

    assert response.status_code == 401


def test_llm_accepts_the_key_as_a_bearer_token():
    # Sin mensajes, la ruta contesta vacío sin llamar a Claude
    response = client.post(
        "/llm/chat/completions",
        json={"messages": []},
        headers={"Authorization": f"Bearer {settings.voice_api_key}"},
    )

    assert response.status_code == 200
    assert response.json()["object"] == "chat.completion"


def test_vapi_accepts_the_key_in_the_vapi_header(monkeypatch):
    monkeypatch.setattr(main, "process_vapi_request", lambda body: {"results": []})

    response = client.post("/vapi", json={}, headers={"X-Vapi-Secret": settings.voice_api_key})

    assert response.status_code == 200
    assert response.json() == {"results": []}


def test_the_bot_refuses_to_start_with_a_short_key(monkeypatch):
    monkeypatch.setenv("VOICE_API_KEY", "demasiado-corta")

    with pytest.raises(ValidationError):
        Settings()


def test_other_routes_do_not_need_the_key():
    assert client.get("/health").status_code == 200
