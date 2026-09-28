import httpx
from config import settings

WHATSAPP_API_URL = (
    f"https://graph.facebook.com/v20.0/{settings.whatsapp_phone_number_id}/messages"
)


async def send_message(to: str, text: str) -> None:
    """Envía un mensaje de texto al número indicado vía WhatsApp Cloud API."""
    headers = {
        "Authorization": f"Bearer {settings.whatsapp_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(WHATSAPP_API_URL, json=payload, headers=headers)
        response.raise_for_status()
