"""Tests for Settings configuration."""

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
    assert s.DATABASE_URL == "postgresql+asyncpg://test:test@localhost/test"
    assert s.SECRET_KEY == "test-secret"
    assert s.FERNET_KEY == VALID_FERNET_KEY
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
    for var in _ENV_VARS_TO_CLEAR:
        monkeypatch.delenv(var, raising=False)
    s = _make_settings()
    assert s.SENTRY_DSN == ""
    assert s.ANTHROPIC_API_KEY == ""


def test_settings_cors_origins_override():
    s = _make_settings(CORS_ORIGINS=["https://helprs.dev", "http://localhost:3000"])
    assert s.CORS_ORIGINS == ["https://helprs.dev", "http://localhost:3000"]
