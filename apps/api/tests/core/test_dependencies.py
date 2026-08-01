"""Tests for the authentication dependencies.

Two paths, deliberately different: the ``get_current_user`` dependency accepts
the ``Authorization`` header only, while ``stream_token`` also accepts
``?access_token=``, because ``EventSource`` cannot set request headers.
"""

import uuid
from datetime import timedelta

import pytest

from helprs.core.config import get_settings
from helprs.core.dependencies import authenticate_token, get_current_user, stream_token
from helprs.core.exceptions import UnauthorizedError
from helprs.core.security import create_access_token


@pytest.fixture
def settings():
    get_settings.cache_clear()
    return get_settings()


class FakeRequest:
    """Only the two attributes the dependencies read."""

    def __init__(self, *, headers: dict[str, str] | None = None, query: dict[str, str] | None = None) -> None:
        self.headers = headers or {}
        self.query_params = query or {}


class FakeUser:
    def __init__(self, user_id: uuid.UUID, login: str) -> None:
        self.id = user_id
        self.github_login = login


class FakeResult:
    def __init__(self, user: FakeUser | None) -> None:
        self._user = user

    def scalar_one_or_none(self) -> FakeUser | None:
        return self._user


class FakeSession:
    """Session double that answers one lookup with a fixed user."""

    def __init__(self, user: FakeUser | None = None) -> None:
        self._user = user
        self.executed: list[object] = []

    async def execute(self, statement) -> FakeResult:
        self.executed.append(statement)
        return FakeResult(self._user)


def _token(settings, login: str = "validuser", **claims) -> tuple[uuid.UUID, str]:
    user_id = uuid.uuid4()
    token = create_access_token(
        {"sub": str(user_id), "github_login": login, **claims},
        settings.SECRET_KEY.get_secret_value(),
    )
    return user_id, token


class TestGetCurrentUser:
    async def test_valid_token_returns_user(self, settings):
        user_id, token = _token(settings)
        session = FakeSession(FakeUser(user_id, "validuser"))

        user = await get_current_user(FakeRequest(headers={"Authorization": f"Bearer {token}"}), session, settings)

        assert user.github_login == "validuser"

    async def test_missing_auth_header(self, settings):
        with pytest.raises(UnauthorizedError, match="Missing or invalid"):
            await get_current_user(FakeRequest(), FakeSession(), settings)

    async def test_invalid_bearer_format(self, settings):
        request = FakeRequest(headers={"Authorization": "Basic abc123"})

        with pytest.raises(UnauthorizedError, match="Missing or invalid"):
            await get_current_user(request, FakeSession(), settings)

    async def test_invalid_jwt(self, settings):
        request = FakeRequest(headers={"Authorization": "Bearer invalid_token"})

        with pytest.raises(UnauthorizedError, match="Invalid or expired"):
            await get_current_user(request, FakeSession(), settings)

    async def test_expired_jwt(self, settings):
        token = create_access_token(
            {"sub": str(uuid.uuid4()), "github_login": "test"},
            settings.SECRET_KEY.get_secret_value(),
            timedelta(seconds=-1),
        )
        request = FakeRequest(headers={"Authorization": f"Bearer {token}"})

        with pytest.raises(UnauthorizedError, match="Invalid or expired"):
            await get_current_user(request, FakeSession(), settings)

    async def test_refresh_token_is_rejected(self, settings):
        _, token = _token(settings, type="refresh")
        request = FakeRequest(headers={"Authorization": f"Bearer {token}"})

        with pytest.raises(UnauthorizedError, match="Cannot use refresh token"):
            await get_current_user(request, FakeSession(), settings)

    async def test_non_uuid_subject_is_rejected(self, settings):
        token = create_access_token({"sub": "not-a-uuid"}, settings.SECRET_KEY.get_secret_value())
        request = FakeRequest(headers={"Authorization": f"Bearer {token}"})

        with pytest.raises(UnauthorizedError, match="Invalid token payload"):
            await get_current_user(request, FakeSession(), settings)

    async def test_user_not_found(self, settings):
        _, token = _token(settings, login="ghost")
        request = FakeRequest(headers={"Authorization": f"Bearer {token}"})

        with pytest.raises(UnauthorizedError, match="User not found"):
            await get_current_user(request, FakeSession(user=None), settings)

    async def test_query_parameter_is_not_accepted(self, settings):
        """A JWT in the URL leaks into proxy logs, history and Referer, so it
        is confined to the streaming dependency below."""
        user_id, token = _token(settings, login="ssouser")
        request = FakeRequest(query={"access_token": token})

        with pytest.raises(UnauthorizedError, match="Missing or invalid"):
            await get_current_user(request, FakeSession(FakeUser(user_id, "ssouser")), settings)


class TestStreamToken:
    """The SSE endpoint extracts the token itself rather than through a
    dependency: a ``Depends(get_db)`` behind an auth dependency would stay
    checked out for the whole stream. ``stream_token`` is that extraction."""

    async def test_accepts_the_query_parameter(self, settings):
        user_id, token = _token(settings, login="ssouser")
        request = FakeRequest(query={"access_token": token})

        user = await authenticate_token(FakeSession(FakeUser(user_id, "ssouser")), settings, stream_token(request))

        assert user.github_login == "ssouser"

    async def test_still_accepts_the_header(self, settings):
        user_id, token = _token(settings, login="headeruser")
        request = FakeRequest(headers={"Authorization": f"Bearer {token}"})

        user = await authenticate_token(FakeSession(FakeUser(user_id, "headeruser")), settings, stream_token(request))

        assert user.github_login == "headeruser"

    async def test_header_wins_over_query_parameter(self, settings):
        user_id, header_token = _token(settings, login="headeruser")
        request = FakeRequest(
            headers={"Authorization": f"Bearer {header_token}"},
            query={"access_token": "garbage-should-be-ignored"},
        )

        user = await authenticate_token(FakeSession(FakeUser(user_id, "headeruser")), settings, stream_token(request))

        assert user.github_login == "headeruser"

    async def test_no_token_at_all_is_rejected(self):
        with pytest.raises(UnauthorizedError, match="Missing or invalid"):
            stream_token(FakeRequest())

    async def test_a_malformed_header_is_rejected_rather_than_ignored(self):
        """Previously the prefix was stripped with removeprefix(), so a bare
        ``Authorization: <token>`` was accepted here but not by the header-only
        dependency -- two notions of a valid header in one module."""
        with pytest.raises(UnauthorizedError, match="Missing or invalid"):
            stream_token(FakeRequest(headers={"Authorization": "Basic abc123"}))
