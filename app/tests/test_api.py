from fastapi.testclient import TestClient

from config import settings
from main import app

client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_webhook_verification_accepts_correct_token():
    # Así comprueba Meta que el webhook es nuestro antes de mandarnos mensajes
    response = client.get("/webhook", params={
        "hub.mode": "subscribe",
        "hub.verify_token": settings.webhook_verify_token,
        "hub.challenge": "12345",
    })

    assert response.status_code == 200
    assert response.text == "12345"


def test_webhook_verification_rejects_wrong_token():
    response = client.get("/webhook", params={
        "hub.mode": "subscribe",
        "hub.verify_token": "token-falso",
        "hub.challenge": "12345",
    })

    assert response.status_code == 403
