"""Unit tests for BYOK service."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from cryptography.fernet import Fernet

from helprs.core.exceptions import BYOKKeyInvalidError, ExternalServiceError
from helprs.core.security import fernet_encrypt
from helprs.modules.installation.models import BYOKConfig
from helprs.modules.installation.service import (
    configure_byok,
    decrypt_byok_key,
    delete_byok_config,
    get_byok_config,
    validate_anthropic_api_key,
)


class TestValidateAnthropicApiKey:
    async def test_valid_key(self):
        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("helprs.modules.installation.service.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await validate_anthropic_api_key("sk-ant-valid-key")
        assert result is True

    async def test_invalid_key_401(self):
        mock_response = MagicMock()
        mock_response.status_code = 401

        with patch("helprs.modules.installation.service.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await validate_anthropic_api_key("sk-ant-invalid")
        assert result is False

    async def test_timeout_raises_external_service_error(self):
        with patch("helprs.modules.installation.service.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.TimeoutException("timeout")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            with pytest.raises(ExternalServiceError, match="temporarily unavailable"):
                await validate_anthropic_api_key("sk-ant-test")


class TestConfigureByok:
    async def test_success(self, db_session, test_installation, settings):
        with patch(
            "helprs.modules.installation.service.validate_anthropic_api_key",
            return_value=True,
        ):
            config = await configure_byok(
                db_session,
                test_installation.id,
                "sk-ant-api03-test1234",
                settings.FERNET_KEY,
            )

        assert config.key_status == "valid"
        assert config.key_hint == "...1234"
        assert config.validated_at is not None
        assert config.installation_id == test_installation.id

    async def test_invalid_key_raises(self, db_session, test_installation, settings):
        with patch(
            "helprs.modules.installation.service.validate_anthropic_api_key",
            return_value=False,
        ):
            with pytest.raises(BYOKKeyInvalidError, match="validation failed"):
                await configure_byok(
                    db_session,
                    test_installation.id,
                    "sk-ant-bad-key",
                    settings.FERNET_KEY,
                )

    async def test_upsert_updates_existing(self, db_session, test_installation, settings):
        with patch(
            "helprs.modules.installation.service.validate_anthropic_api_key",
            return_value=True,
        ):
            config1 = await configure_byok(
                db_session,
                test_installation.id,
                "sk-ant-api03-firstkey1",
                settings.FERNET_KEY,
            )
            config2 = await configure_byok(
                db_session,
                test_installation.id,
                "sk-ant-api03-secondk2",
                settings.FERNET_KEY,
            )

        assert config1.id == config2.id
        assert config2.key_hint == "...ndk2"


class TestDecryptByokKey:
    def test_success(self, settings):
        api_key = "sk-ant-api03-testkey123"
        encrypted = fernet_encrypt(api_key, settings.FERNET_KEY)
        config = BYOKConfig(
            installation_id="00000000-0000-0000-0000-000000000000",
            encrypted_api_key=encrypted,
            key_status="valid",
        )
        result = decrypt_byok_key(config, settings.FERNET_KEY)
        assert result == api_key

    def test_corrupted_raises(self, settings):
        config = BYOKConfig(
            installation_id="00000000-0000-0000-0000-000000000000",
            encrypted_api_key="not-valid-ciphertext",
            key_status="valid",
        )
        with pytest.raises(BYOKKeyInvalidError, match="could not be decrypted"):
            decrypt_byok_key(config, settings.FERNET_KEY)


class TestDeleteByokConfig:
    async def test_deletes_existing(self, db_session, test_installation, settings):
        with patch(
            "helprs.modules.installation.service.validate_anthropic_api_key",
            return_value=True,
        ):
            await configure_byok(
                db_session,
                test_installation.id,
                "sk-ant-api03-deltest1",
                settings.FERNET_KEY,
            )

        result = await delete_byok_config(db_session, test_installation.id)
        assert result is True

        config = await get_byok_config(db_session, test_installation.id)
        assert config is None

    async def test_nonexistent_returns_false(self, db_session, test_installation):
        result = await delete_byok_config(db_session, test_installation.id)
        assert result is False
