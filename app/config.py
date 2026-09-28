from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    whatsapp_token: str
    whatsapp_phone_number_id: str
    webhook_verify_token: str
    anthropic_api_key: str
    # En modo multi-profesional los calendarios vienen de BUSINESS_CONFIG, así que
    # esta variable es opcional (solo se usa en modo de un único calendario).
    google_calendar_id: str = ""
    google_credentials_json: str = "credentials.json"


settings = Settings()
