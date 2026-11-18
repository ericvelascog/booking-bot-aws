"""Configuración común a todos los tests.

config.py exige las claves (WhatsApp, Anthropic...) en cuanto se importa.
Los tests no usan claves reales ni llaman a internet, así que ponemos valores
de mentira ANTES de que pytest importe el código de la app.
"""
import os
import sys
from pathlib import Path

# Los módulos de la app (main.py, config.py...) viven en app/, un nivel por encima
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("WHATSAPP_TOKEN", "test-token")
os.environ.setdefault("WHATSAPP_PHONE_NUMBER_ID", "000000")
os.environ.setdefault("WHATSAPP_APP_SECRET", "0123456789abcdef" * 2)  # 32 caracteres, como el de Meta
os.environ.setdefault("WEBHOOK_VERIFY_TOKEN", "test-verify-token")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("VOICE_API_KEY", "test-voice-key-" + "x" * 32)  # mínimo 32 caracteres

# Las conversaciones se guardan en memoria salvo en los tests que piden
# DynamoDB (y esos usan moto, una DynamoDB de mentira)
os.environ.pop("SESSIONS_TABLE", None)
