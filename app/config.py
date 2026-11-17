from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # extra="ignore": el .env también lleva variables que leen otros módulos
    # (GOOGLE_CREDENTIALS_CONTENT, BUSINESS_CONFIG); sin esto, arrancar con
    # ese .env falla con "Extra inputs are not permitted".
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    whatsapp_token: str
    whatsapp_phone_number_id: str
    webhook_verify_token: str
    anthropic_api_key: str
    # La clave que exigen /llm y /vapi (security.py). Obligatoria y de 32
    # caracteres como mínimo: si falta o es corta, el bot no arranca, en vez de
    # arrancar con esas rutas abiertas o protegidas con una clave fácil
    voice_api_key: str = Field(min_length=32)
    # En modo multi-profesional los calendarios vienen de BUSINESS_CONFIG, así que
    # esta variable es opcional (solo se usa en modo de un único calendario).
    google_calendar_id: str = ""
    google_credentials_json: str = "credentials.json"


settings = Settings()
