"""Application configuration via pydantic-settings."""

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    DATABASE_URL: str

    # Security
    SECRET_KEY: str
    FERNET_KEY: str
    ADMIN_PASSWORD: str = ""

    # GitHub App
    GITHUB_APP_ID: str
    GITHUB_APP_PRIVATE_KEY: str = ""
    GITHUB_CLIENT_ID: str = ""
    GITHUB_CLIENT_SECRET: str = ""
    GITHUB_WEBHOOK_SECRET: str = ""

    # Anthropic
    ANTHROPIC_API_KEY: str = ""

    # Lemon Squeezy
    LEMONSQUEEZY_API_KEY: str = ""
    LEMONSQUEEZY_WEBHOOK_SECRET: str = ""

    # Sentry
    SENTRY_DSN: str = ""

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]

    # Frontend base URL used to build user-facing links (e.g. PR-comment session links).
    # Kept separate from CORS_ORIGINS: that list is for browser security, this single
    # string is for link composition. See deferred-work.md nice-to-have #11.
    APP_BASE_URL: str = "http://localhost:5173"

    # Environment
    ENVIRONMENT: str = "development"

    @field_validator("FERNET_KEY")
    @classmethod
    def validate_fernet_key(cls, v: str) -> str:
        """Validate that FERNET_KEY is a valid Fernet key (32 url-safe base64 bytes)."""
        from cryptography.fernet import Fernet, InvalidToken

        try:
            Fernet(v.encode() if isinstance(v, str) else v)
        except (ValueError, InvalidToken) as e:
            raise ValueError(
                "FERNET_KEY must be a valid Fernet key (32 url-safe base64-encoded bytes). "
                "Generate with: python -c "
                "'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
            ) from e
        return v


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()
