"""Unit tests for identity use cases.

The GitHub boundary has its own tests (``test_github.py``); here the network
is served by a double so these exercise orchestration and persistence.
"""

import uuid
from datetime import timedelta

import httpx
import pytest

from helprs.core.exceptions import UnauthorizedError
from helprs.core.security import create_access_token, decode_access_token, fernet_encrypt
from helprs.modules.identity.github import GitHubUserProfile
from helprs.modules.identity.models import GitHubUser
from helprs.modules.identity.service import (
    TokenPair,
    authenticate_with_code,
    create_token_pair,
    get_decrypted_github_token,
    refresh_tokens,
    sync_user,
)


class StoredUser:
    """Stand-in for a GitHubUser row where no database is needed."""

    def __init__(self, *, encrypted_token: str = "", user_id: uuid.UUID | None = None) -> None:
        self.id = user_id or uuid.uuid4()
        self.github_login = "testuser"
        self.github_access_token_enc = encrypted_token


def _serve_oauth(monkeypatch, *, profile_id: int = 99999999, login: str = "newuser") -> None:
    """Serve both GitHub calls the login flow makes."""

    def _handle(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/access_token"):
            return httpx.Response(200, json={"access_token": "gho_from_code", "token_type": "bearer"})
        return httpx.Response(
            200,
            json={"id": profile_id, "login": login, "email": f"{login}@example.com", "avatar_url": None},
        )

    original = httpx.AsyncClient

    def _client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(_handle)
        return original(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", _client)


class TestAuthenticateWithCode:
    async def test_creates_user_and_issues_tokens(self, db_session, settings, monkeypatch):
        _serve_oauth(monkeypatch, profile_id=13579, login="freshuser")

        user, tokens = await authenticate_with_code(db_session, "the-code", settings)

        assert user.github_id == 13579
        assert user.github_login == "freshuser"
        assert isinstance(tokens, TokenPair)
        assert decode_access_token(tokens.access_token, settings.SECRET_KEY.get_secret_value())["sub"] == str(user.id)

    async def test_stores_the_github_token_encrypted(self, db_session, settings, monkeypatch):
        _serve_oauth(monkeypatch, profile_id=24680, login="encrypteduser")

        user, _ = await authenticate_with_code(db_session, "the-code", settings)

        assert user.github_access_token_enc != "gho_from_code"
        assert get_decrypted_github_token(user, settings.FERNET_KEY.get_secret_value()) == "gho_from_code"


class TestSyncUser:
    async def test_creates_new_user(self, db_session, settings):
        profile = GitHubUserProfile(
            id=99999999,
            login="newuser",
            email="new@example.com",
            avatar_url="https://avatars.example/u/99999999",
        )

        user = await sync_user(db_session, profile, "gho_new_token", settings)

        assert user.github_id == 99999999
        assert user.github_login == "newuser"
        assert user.email == "new@example.com"

    async def test_updates_existing_user(self, db_session, settings, test_user):
        existing_user, _ = test_user
        profile = GitHubUserProfile(
            id=existing_user.github_id,
            login="updated_login",
            email="updated@example.com",
            avatar_url=None,
        )

        user = await sync_user(db_session, profile, "gho_updated_token", settings)

        assert user.id == existing_user.id
        assert user.github_login == "updated_login"
        assert user.email == "updated@example.com"

    async def test_does_not_duplicate_on_repeated_login(self, db_session, settings):
        profile = GitHubUserProfile(id=555000, login="repeat", email=None, avatar_url=None)

        first = await sync_user(db_session, profile, "gho_1", settings)
        second = await sync_user(db_session, profile, "gho_2", settings)

        assert first.id == second.id


class TestCreateTokenPair:
    def test_access_and_refresh_differ_and_carry_the_right_claims(self, settings):
        user = StoredUser()

        pair = create_token_pair(user, settings)

        assert pair.access_token != pair.refresh_token
        access_claims = decode_access_token(pair.access_token, settings.SECRET_KEY.get_secret_value())
        refresh_claims = decode_access_token(pair.refresh_token, settings.SECRET_KEY.get_secret_value())
        assert access_claims["github_login"] == "testuser"
        assert "type" not in access_claims
        assert refresh_claims["type"] == "refresh"


class TestRefreshTokens:
    async def test_valid_refresh_returns_a_new_pair(self, db_session, settings, test_user):
        user, _ = test_user
        refresh_token = create_access_token(
            {"sub": str(user.id), "type": "refresh"},
            settings.SECRET_KEY.get_secret_value(),
            timedelta(days=7),
        )

        pair = await refresh_tokens(refresh_token, db_session, settings)

        assert isinstance(pair, TokenPair)
        assert decode_access_token(pair.access_token, settings.SECRET_KEY.get_secret_value())["sub"] == str(user.id)

    async def test_invalid_refresh_token(self, db_session, settings):
        with pytest.raises(UnauthorizedError, match="Invalid or expired"):
            await refresh_tokens("invalid_token", db_session, settings)

    async def test_access_token_is_not_accepted_as_refresh(self, db_session, settings, test_user):
        _, access_token = test_user

        with pytest.raises(UnauthorizedError, match="not a refresh token"):
            await refresh_tokens(access_token, db_session, settings)

    async def test_user_not_found(self, db_session, settings):
        refresh_token = create_access_token(
            {"sub": str(uuid.uuid4()), "type": "refresh"},
            settings.SECRET_KEY.get_secret_value(),
            timedelta(days=7),
        )

        with pytest.raises(UnauthorizedError, match="User not found"):
            await refresh_tokens(refresh_token, db_session, settings)

    async def test_non_uuid_subject_is_rejected(self, db_session, settings):
        refresh_token = create_access_token(
            {"sub": "not-a-uuid", "type": "refresh"},
            settings.SECRET_KEY.get_secret_value(),
            timedelta(days=7),
        )

        with pytest.raises(UnauthorizedError, match="Invalid refresh token payload"):
            await refresh_tokens(refresh_token, db_session, settings)

    async def test_missing_subject_is_rejected(self, db_session, settings):
        secret = settings.SECRET_KEY.get_secret_value()
        refresh_token = create_access_token({"type": "refresh"}, secret, timedelta(days=7))

        with pytest.raises(UnauthorizedError, match="Invalid refresh token payload"):
            await refresh_tokens(refresh_token, db_session, settings)


class TestGetDecryptedGithubToken:
    def test_valid_token(self, settings):
        user = StoredUser(encrypted_token=fernet_encrypt("gho_test", settings.FERNET_KEY.get_secret_value()))

        assert get_decrypted_github_token(user, settings.FERNET_KEY.get_secret_value()) == "gho_test"

    def test_corrupted_token(self, settings):
        user = StoredUser(encrypted_token="corrupted_data")

        with pytest.raises(UnauthorizedError, match="corrupted"):
            get_decrypted_github_token(user, settings.FERNET_KEY.get_secret_value())


class TestUserStats:
    async def test_empty_when_user_has_no_installations(self, db_session, settings, monkeypatch):
        from helprs.modules.identity import service

        async def _no_installations(session, user, settings):
            return []

        monkeypatch.setattr(
            "helprs.modules.installation.service.get_installations_for_user",
            _no_installations,
        )

        stats = await service.get_user_stats(db_session, GitHubUser(github_id=1, github_login="x"), settings)

        assert stats.totals.total == 0
        assert stats.daily_counts == []
