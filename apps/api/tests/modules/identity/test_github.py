"""Tests for the typed GitHub boundary.

Requests go through ``httpx.MockTransport``, so these exercise the real
request building and the real response parsing.
"""

import httpx
import pytest

from helprs.core.exceptions import ExternalServiceError, UnauthorizedError
from helprs.modules.identity.github import (
    GitHubOAuthToken,
    GitHubUserProfile,
    exchange_code_for_token,
    fetch_user_profile,
)


def _serving(handler, monkeypatch) -> list[httpx.Request]:
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


class TestExchangeCodeForToken:
    async def test_returns_typed_token_and_sends_credentials(self, settings, monkeypatch):
        seen = _serving(
            lambda _: httpx.Response(200, json={"access_token": "gho_abc123", "token_type": "bearer"}),
            monkeypatch,
        )

        token = await exchange_code_for_token("the-code", settings)

        assert isinstance(token, GitHubOAuthToken)
        assert token.access_token == "gho_abc123"
        assert b"code=the-code" in seen[0].content

    async def test_oauth_error_payload_is_unauthorized(self, settings, monkeypatch):
        """GitHub answers 200 with an error key for a bad or expired code."""
        _serving(lambda _: httpx.Response(200, json={"error": "bad_verification_code"}), monkeypatch)

        with pytest.raises(UnauthorizedError, match="bad_verification_code"):
            await exchange_code_for_token("stale", settings)

    async def test_unexpected_shape_is_rejected_at_the_edge(self, settings, monkeypatch):
        """A missing access_token must fail here, not as a KeyError later."""
        _serving(lambda _: httpx.Response(200, json={"unexpected": "shape"}), monkeypatch)

        with pytest.raises(ExternalServiceError, match="Unexpected OAuth token payload"):
            await exchange_code_for_token("code", settings)

    async def test_http_error_is_external_service_error(self, settings, monkeypatch):
        _serving(lambda _: httpx.Response(500), monkeypatch)

        with pytest.raises(ExternalServiceError, match="token exchange failed"):
            await exchange_code_for_token("code", settings)

    async def test_timeout_is_external_service_error(self, settings, monkeypatch):
        def _timeout(request: httpx.Request) -> httpx.Response:
            raise httpx.TimeoutException("too slow", request=request)

        _serving(_timeout, monkeypatch)

        with pytest.raises(ExternalServiceError, match="temporarily unavailable"):
            await exchange_code_for_token("code", settings)


class TestFetchUserProfile:
    async def test_maps_github_id_and_sends_bearer_token(self, monkeypatch):
        seen = _serving(
            lambda _: httpx.Response(
                200,
                json={
                    "id": 4242,
                    "login": "octocat",
                    "email": "octo@example.com",
                    "avatar_url": "https://avatars.example/u/4242",
                },
            ),
            monkeypatch,
        )

        profile = await fetch_user_profile("gho_token")

        assert isinstance(profile, GitHubUserProfile)
        assert profile.github_id == 4242
        assert profile.login == "octocat"
        assert seen[0].headers["Authorization"] == "Bearer gho_token"

    async def test_optional_fields_default_to_none(self, monkeypatch):
        _serving(lambda _: httpx.Response(200, json={"id": 1, "login": "minimal"}), monkeypatch)

        profile = await fetch_user_profile("gho_token")

        assert profile.email is None
        assert profile.avatar_url is None

    async def test_401_is_unauthorized(self, monkeypatch):
        _serving(lambda _: httpx.Response(401), monkeypatch)

        with pytest.raises(UnauthorizedError, match="invalid or revoked"):
            await fetch_user_profile("bad_token")

    async def test_5xx_is_external_service_error(self, monkeypatch):
        _serving(lambda _: httpx.Response(503), monkeypatch)

        with pytest.raises(ExternalServiceError, match="GitHub API error"):
            await fetch_user_profile("gho_token")

    async def test_timeout_is_external_service_error(self, monkeypatch):
        def _timeout(request: httpx.Request) -> httpx.Response:
            raise httpx.TimeoutException("too slow", request=request)

        _serving(_timeout, monkeypatch)

        with pytest.raises(ExternalServiceError, match="temporarily unavailable"):
            await fetch_user_profile("gho_token")

    async def test_missing_id_is_rejected_at_the_edge(self, monkeypatch):
        _serving(lambda _: httpx.Response(200, json={"login": "no-id"}), monkeypatch)

        with pytest.raises(ExternalServiceError, match="Unexpected user payload"):
            await fetch_user_profile("gho_token")
