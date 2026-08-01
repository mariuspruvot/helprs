"""Application configuration via pydantic-settings."""

import base64
from functools import lru_cache
from typing import Literal

from cryptography.fernet import Fernet, InvalidToken
from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration.

    Every credential is a ``SecretStr`` so it cannot be rendered by accident.
    ``repr(Settings())`` used to print all of them in cleartext, and
    ``sentry_sdk.init`` defaults to ``include_local_variables=True`` -- a live
    ``settings`` local sits in a dozen frames that can raise, so one unhandled
    500 was enough to ship the whole secret set to a third party. Read a value
    with ``.get_secret_value()``; ``SecretStr`` defines ``__len__``, so plain
    truthiness checks still work.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    DATABASE_URL: SecretStr

    # Security
    SECRET_KEY: SecretStr
    FERNET_KEY: SecretStr
    ADMIN_PASSWORD: SecretStr = SecretStr("")

    # GitHub App
    GITHUB_APP_ID: str
    GITHUB_APP_PRIVATE_KEY: SecretStr = SecretStr("")
    GITHUB_CLIENT_ID: str = ""
    GITHUB_CLIENT_SECRET: SecretStr = SecretStr("")
    GITHUB_WEBHOOK_SECRET: SecretStr = SecretStr("")

    # Sentry
    SENTRY_DSN: SecretStr = SecretStr("")

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]

    # Frontend base URL used to build user-facing links (e.g. PR-comment session links).
    # Kept separate from CORS_ORIGINS: that list is for browser security, this single
    # string is for link composition.
    APP_BASE_URL: str = "http://localhost:5173"

    # Container orchestration
    CONTAINER_TTL_SECONDS: int = 900  # 15 minutes

    # Database pool, per uvicorn worker. workers x (size + overflow) must stay
    # below the server's max_connections.
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 5

    # Environment. A Literal rather than a free-form str: validate_production_secrets
    # below only fires on the exact string "production", so a typo like "prod" would
    # silently disable the one guard meant to fail loud at startup.
    ENVIRONMENT: Literal["development", "test", "production"] = "development"

    @field_validator("GITHUB_APP_PRIVATE_KEY")
    @classmethod
    def normalize_private_key(cls, v: SecretStr) -> SecretStr:
        """Accept the App private key as raw PEM or base64-encoded PEM.

        ``.env`` files cannot hold multi-line values, so operators base64 the
        PEM; platforms with multi-line env vars (Coolify) paste it raw. Both
        are normalized to raw PEM here so the rest of the code only ever sees
        what ``jwt.encode`` expects.
        """
        raw = v.get_secret_value().strip()
        if not raw or raw.startswith("-----BEGIN"):
            return SecretStr(raw)

        try:
            decoded = base64.b64decode(raw, validate=True).decode()
        except (ValueError, UnicodeDecodeError) as e:
            raise ValueError(
                "GITHUB_APP_PRIVATE_KEY must be a PEM private key, either raw "
                "(starting with '-----BEGIN') or base64-encoded. Generate with: "
                "base64 -i your-app.private-key.pem | tr -d '\\n'"
            ) from e

        if not decoded.lstrip().startswith("-----BEGIN"):
            raise ValueError("GITHUB_APP_PRIVATE_KEY decoded from base64 but is not a PEM private key")
        return SecretStr(decoded)

    @field_validator("FERNET_KEY")
    @classmethod
    def validate_fernet_key(cls, v: SecretStr) -> SecretStr:
        """Validate that FERNET_KEY is a valid Fernet key (32 url-safe base64 bytes)."""
        try:
            Fernet(v.get_secret_value().encode())
        except (ValueError, InvalidToken) as e:
            raise ValueError(
                "FERNET_KEY must be a valid Fernet key (32 url-safe base64-encoded bytes). "
                "Generate with: python -c "
                "'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
            ) from e
        return v

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        """Enforce that critical secrets are set when ENVIRONMENT is production."""
        if self.ENVIRONMENT != "production":
            return self
        missing: list[str] = []
        if not self.ADMIN_PASSWORD:
            missing.append("ADMIN_PASSWORD")
        if len(self.SECRET_KEY.get_secret_value()) < 32:
            missing.append("SECRET_KEY (must be >= 32 characters)")
        if not self.GITHUB_WEBHOOK_SECRET:
            missing.append("GITHUB_WEBHOOK_SECRET")
        if not self.GITHUB_APP_PRIVATE_KEY:
            missing.append("GITHUB_APP_PRIVATE_KEY")
        if not self.GITHUB_CLIENT_ID:
            missing.append("GITHUB_CLIENT_ID")
        if not self.GITHUB_CLIENT_SECRET:
            missing.append("GITHUB_CLIENT_SECRET")
        if missing:
            raise ValueError(f"Production environment requires: {', '.join(missing)}")
        return self


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()
