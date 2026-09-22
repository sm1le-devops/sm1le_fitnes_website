from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # App
    secret_key: str = ""
    your_domain: str = "http://localhost:8000"
    render_external_url: str = ""

    # Security
    csrf_secret: str
    jwt_secret_key: str

    # Stripe
    stripe_secret_key: str = ""
    stripe_publishable_key: str = ""
    stripe_webhook_secret: str = ""

    # Mail
    mail_user: str = ""
    mail_password: str = ""
    mail_from: str = ""
    mail_server: str = "smtp.gmail.com"
    mail_port: int = 587

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Database
    database_url: str

    db_name: str = ""
    db_host: str = ""
    db_port: int = 5432
    db_user: str = ""
    db_password: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


# Values required by Settings are loaded from environment variables at runtime.
# Mypy cannot infer BaseSettings environment loading from a zero-argument call.
settings = Settings()  # type: ignore[call-arg]