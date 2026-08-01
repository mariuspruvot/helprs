"""Tests for Settings configuration."""

import base64

import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError

from helprs.core.config import Settings

VALID_FERNET_KEY = Fernet.generate_key().decode()

# Env vars that conftest sets and pydantic-settings would pick up
_ENV_VARS_TO_CLEAR = ("DATABASE_URL", "SECRET_KEY", "FERNET_KEY", "GITHUB_APP_ID", "ENVIRONMENT")


def _make_settings(**overrides) -> Settings:
    defaults = {
        "DATABASE_URL": "postgresql+asyncpg://test:test@localhost/test",
        "SECRET_KEY": "test-secret",
        "FERNET_KEY": VALID_FERNET_KEY,
        "GITHUB_APP_ID": "000000",
    }
    defaults.update(overrides)
    return Settings(**defaults)


def test_settings_loads_with_valid_values(monkeypatch):
    for var in _ENV_VARS_TO_CLEAR:
        monkeypatch.delenv(var, raising=False)
    s = _make_settings()
    assert s.DATABASE_URL.get_secret_value() == "postgresql+asyncpg://test:test@localhost/test"
    assert s.SECRET_KEY.get_secret_value() == "test-secret"
    assert s.FERNET_KEY.get_secret_value() == VALID_FERNET_KEY
    assert s.ENVIRONMENT == "development"
    assert s.CORS_ORIGINS == ["http://localhost:5173"]


def test_settings_missing_required_database_url(monkeypatch):
    for var in _ENV_VARS_TO_CLEAR:
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(ValidationError) as exc_info:
        Settings(SECRET_KEY="x", FERNET_KEY=VALID_FERNET_KEY, GITHUB_APP_ID="x")
    assert "DATABASE_URL" in str(exc_info.value)


def test_settings_missing_required_secret_key(monkeypatch):
    for var in _ENV_VARS_TO_CLEAR:
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(ValidationError) as exc_info:
        Settings(DATABASE_URL="postgresql+asyncpg://x:x@localhost/x", FERNET_KEY=VALID_FERNET_KEY, GITHUB_APP_ID="x")
    assert "SECRET_KEY" in str(exc_info.value)


def test_settings_missing_required_fernet_key(monkeypatch):
    for var in _ENV_VARS_TO_CLEAR:
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(ValidationError) as exc_info:
        Settings(DATABASE_URL="postgresql+asyncpg://x:x@localhost/x", SECRET_KEY="x", GITHUB_APP_ID="x")
    assert "FERNET_KEY" in str(exc_info.value)


def test_settings_invalid_fernet_key_rejected():
    with pytest.raises(ValidationError, match="FERNET_KEY must be a valid Fernet key"):
        _make_settings(FERNET_KEY="not-a-valid-fernet-key")


def test_settings_extra_env_vars_ignored():
    s = _make_settings(UNKNOWN_VAR="should-be-ignored")
    assert not hasattr(s, "UNKNOWN_VAR")


def test_settings_optional_fields_default_empty(monkeypatch):
    for var in (*_ENV_VARS_TO_CLEAR, "GITHUB_CLIENT_SECRET"):
        monkeypatch.delenv(var, raising=False)
    s = _make_settings()
    assert s.SENTRY_DSN.get_secret_value() == ""
    assert s.GITHUB_CLIENT_SECRET.get_secret_value() == ""


def test_settings_cors_origins_override():
    s = _make_settings(CORS_ORIGINS=["https://helprs.dev", "http://localhost:3000"])
    assert s.CORS_ORIGINS == ["https://helprs.dev", "http://localhost:3000"]


PEM = "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA\n-----END RSA PRIVATE KEY-----\n"


def test_private_key_raw_pem_passes_through():
    assert PEM.strip() == _make_settings(GITHUB_APP_PRIVATE_KEY=PEM).GITHUB_APP_PRIVATE_KEY.get_secret_value()


def test_private_key_base64_is_decoded():
    encoded = base64.b64encode(PEM.encode()).decode()
    assert _make_settings(GITHUB_APP_PRIVATE_KEY=encoded).GITHUB_APP_PRIVATE_KEY.get_secret_value() == PEM


def test_private_key_empty_stays_empty():
    assert _make_settings(GITHUB_APP_PRIVATE_KEY="").GITHUB_APP_PRIVATE_KEY.get_secret_value() == ""


def test_private_key_garbage_is_rejected():
    with pytest.raises(ValidationError, match="must be a PEM private key"):
        _make_settings(GITHUB_APP_PRIVATE_KEY="not base64 and not pem!!")


def test_private_key_base64_of_non_pem_is_rejected():
    encoded = base64.b64encode(b"just some bytes").decode()
    with pytest.raises(ValidationError, match="is not a PEM private key"):
        _make_settings(GITHUB_APP_PRIVATE_KEY=encoded)


def test_production_requires_secrets():
    with pytest.raises(ValidationError, match="Production environment requires"):
        _make_settings(ENVIRONMENT="production")


def test_production_accepts_complete_config():
    s = _make_settings(
        ENVIRONMENT="production",
        SECRET_KEY="x" * 32,
        ADMIN_PASSWORD="admin-password",
        GITHUB_WEBHOOK_SECRET="webhook-secret",
        GITHUB_APP_PRIVATE_KEY=PEM,
        GITHUB_CLIENT_ID="client-id",
        GITHUB_CLIENT_SECRET="client-secret",
    )
    assert s.ENVIRONMENT == "production"


def test_production_error_lists_every_missing_secret():
    """One boot, one complete list — an operator should not fix them one by one."""
    with pytest.raises(ValidationError) as exc_info:
        _make_settings(
            ENVIRONMENT="production",
            SECRET_KEY="too-short",
            ADMIN_PASSWORD="",
            GITHUB_WEBHOOK_SECRET="",
            GITHUB_APP_PRIVATE_KEY="",
            GITHUB_CLIENT_ID="",
            GITHUB_CLIENT_SECRET="",
        )
    message = str(exc_info.value)
    for expected in (
        "ADMIN_PASSWORD",
        "SECRET_KEY",
        "GITHUB_WEBHOOK_SECRET",
        "GITHUB_APP_PRIVATE_KEY",
        "GITHUB_CLIENT_ID",
        "GITHUB_CLIENT_SECRET",
    ):
        assert expected in message


def test_secrets_are_masked_in_repr():
    """Regression: every credential used to render in cleartext.

    sentry_sdk.init defaults to include_local_variables=True and a live
    ``settings`` sits in a dozen frames that can raise, so one unhandled 500
    was enough to upload the whole secret set to a third party.
    """
    s = _make_settings(
        DATABASE_URL="postgresql+asyncpg://u:pgpassw0rd@h/d",
        SECRET_KEY="secret-key-value",
        ADMIN_PASSWORD="admin-password-value",
        GITHUB_CLIENT_SECRET="client-secret-value",
        GITHUB_WEBHOOK_SECRET="webhook-secret-value",
        SENTRY_DSN="https://sentry-key@example.com/1",
    )
    rendered = f"{s!r} {s} {s.model_dump()}"

    for leaked in (
        "pgpassw0rd",
        "secret-key-value",
        "admin-password-value",
        "client-secret-value",
        "webhook-secret-value",
        "sentry-key",
        VALID_FERNET_KEY,
    ):
        assert leaked not in rendered

    # Still readable on purpose.
    assert s.SECRET_KEY.get_secret_value() == "secret-key-value"


def test_environment_rejects_unknown_values():
    """A typo like "prod" would silently skip validate_production_secrets,
    which is the one guard meant to fail loud at startup."""
    with pytest.raises(ValidationError):
        _make_settings(ENVIRONMENT="prod")
