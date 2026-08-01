"""Tests for BYOK credential storage and validation."""

import httpx
import pytest

from helprs.core.exceptions import BYOKKeyInvalidError, ExternalServiceError
from helprs.core.security import fernet_encrypt
from helprs.modules.installation.anthropic import is_credential_valid, is_oauth_token
from helprs.modules.installation.models import BYOKConfig
from helprs.modules.installation.service import (
    configure_byok,
    decrypt_byok_key,
    delete_byok_config,
    get_byok_config,
)
from tests.github_double import serving_github

_UNUSED_INSTALLATION_ID = "00000000-0000-0000-0000-000000000000"


def _serving_anthropic(handler, monkeypatch) -> list[httpx.Request]:
    seen: list[httpx.Request] = []

    def _record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    original = httpx.AsyncClient

    def _client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(_record)
        return original(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", _client)
    return seen


class TestIsCredentialValid:
    async def test_accepted_api_key_sends_the_key_header(self, monkeypatch):
        seen = _serving_anthropic(lambda _: httpx.Response(200, json={}), monkeypatch)

        assert await is_credential_valid("sk-ant-api03-valid") is True
        assert seen[0].headers["x-api-key"] == "sk-ant-api03-valid"
        assert seen[0].url.path == "/v1/models"

    @pytest.mark.parametrize("status", [401, 403])
    async def test_rejected_api_key(self, monkeypatch, status):
        _serving_anthropic(lambda _: httpx.Response(status, json={}), monkeypatch)

        assert await is_credential_valid("sk-ant-api03-invalid") is False

    async def test_oauth_token_skips_the_api_call(self, monkeypatch):
        """OAuth tokens are rejected by the REST API, so they can only be
        validated at runtime by the CLI inside the container."""
        seen = _serving_anthropic(lambda _: httpx.Response(500), monkeypatch)

        assert await is_credential_valid("sk-ant-oat01-fakeoauthtoken") is True
        assert seen == []

    async def test_timeout_is_external_service_error(self, monkeypatch):
        def _timeout(request: httpx.Request) -> httpx.Response:
            raise httpx.TimeoutException("too slow", request=request)

        _serving_anthropic(_timeout, monkeypatch)

        with pytest.raises(ExternalServiceError, match="temporarily unavailable"):
            await is_credential_valid("sk-ant-api03-test")

    async def test_5xx_is_external_service_error(self, monkeypatch):
        _serving_anthropic(lambda _: httpx.Response(503), monkeypatch)

        with pytest.raises(ExternalServiceError, match="Anthropic API error"):
            await is_credential_valid("sk-ant-api03-test")

    def test_oauth_prefix_detection(self):
        assert is_oauth_token("sk-ant-oat01-abc") is True
        assert is_oauth_token("sk-ant-api03-abc") is False


class TestConfigureByok:
    async def test_stores_hint_and_status(self, db_session, test_installation, settings):
        with serving_github(claude_key_valid=True):
            config = await configure_byok(
                db_session,
                test_installation.id,
                "sk-ant-api03-test1234",
                settings.FERNET_KEY.get_secret_value(),
            )

        assert config.key_status == "valid"
        assert config.key_hint == "...1234"
        assert config.validated_at is not None
        assert config.installation_id == test_installation.id

    async def test_never_stores_the_key_in_clear(self, db_session, test_installation, settings):
        with serving_github(claude_key_valid=True):
            config = await configure_byok(
                db_session,
                test_installation.id,
                "sk-ant-api03-secret99",
                settings.FERNET_KEY.get_secret_value(),
            )

        assert "sk-ant-api03-secret99" not in config.encrypted_api_key
        assert decrypt_byok_key(config, settings.FERNET_KEY.get_secret_value()) == "sk-ant-api03-secret99"

    async def test_invalid_key_raises(self, db_session, test_installation, settings):
        with serving_github(claude_key_valid=False), pytest.raises(BYOKKeyInvalidError, match="validation failed"):
            await configure_byok(
                db_session,
                test_installation.id,
                "sk-ant-api03-badkey0",
                settings.FERNET_KEY.get_secret_value(),
            )

    async def test_upsert_updates_existing(self, db_session, test_installation, settings):
        with serving_github(claude_key_valid=True):
            first = await configure_byok(
                db_session,
                test_installation.id,
                "sk-ant-api03-firstkey1",
                settings.FERNET_KEY.get_secret_value(),
            )
            second = await configure_byok(
                db_session,
                test_installation.id,
                "sk-ant-api03-secondk2",
                settings.FERNET_KEY.get_secret_value(),
            )

        assert first.id == second.id
        assert second.key_hint == "...ndk2"


class TestDecryptByokKey:
    def test_round_trip(self, settings):
        api_key = "sk-ant-api03-testkey123"
        config = BYOKConfig(
            installation_id=_UNUSED_INSTALLATION_ID,
            encrypted_api_key=fernet_encrypt(api_key, settings.FERNET_KEY.get_secret_value()),
            key_status="valid",
        )

        assert decrypt_byok_key(config, settings.FERNET_KEY.get_secret_value()) == api_key

    def test_corrupted_ciphertext_raises(self, settings):
        config = BYOKConfig(
            installation_id=_UNUSED_INSTALLATION_ID,
            encrypted_api_key="not-valid-ciphertext",
            key_status="valid",
        )

        with pytest.raises(BYOKKeyInvalidError, match="could not be decrypted"):
            decrypt_byok_key(config, settings.FERNET_KEY.get_secret_value())


class TestDeleteByokConfig:
    async def test_deletes_existing(self, db_session, test_installation, settings):
        with serving_github(claude_key_valid=True):
            await configure_byok(
                db_session,
                test_installation.id,
                "sk-ant-api03-deltest1",
                settings.FERNET_KEY.get_secret_value(),
            )

        assert await delete_byok_config(db_session, test_installation.id) is True
        assert await get_byok_config(db_session, test_installation.id) is None

    async def test_nonexistent_returns_false(self, db_session, test_installation):
        assert await delete_byok_config(db_session, test_installation.id) is False
