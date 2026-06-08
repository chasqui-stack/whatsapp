from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Server
    port: int = 8000

    # WhatsApp Business API
    wa_phone_id: str | None = None
    wa_token: str
    wa_verify_token: str
    wa_app_id: int
    wa_app_secret: str
    wa_callback_url: str | None = None
    wa_waba_id: str | None = None

    # Chasqui core
    core_url: str = "http://localhost:8090"
    internal_api_key: str = ""

    # Sentry
    sentry_dsn: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
