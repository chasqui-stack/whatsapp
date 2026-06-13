from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # User-facing gateway fallbacks. English by default (English-only codebase);
    # set them in your users' language via .env — the same posture as the core's
    # FALLBACK_REPLY. The agent itself localizes via the DB system prompt; these
    # only fire when the core is unreachable or a message type isn't handled.
    error_reply: str = (
        "Sorry, we hit a technical issue. Please try again in a few minutes."
    )
    unsupported_reply: str = (
        "For now I only handle text, audio, images and buttons. "
        "Send me a message and I'll be glad to help."
    )

    # Sentry
    sentry_dsn: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
