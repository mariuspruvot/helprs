"""Tests for ``fetch_pr_diff`` (Story 3.1).

Uses ``httpx.MockTransport`` for zero-new-deps mocking. Tests patch the
module-level ``httpx.AsyncClient`` so the wrapper's own
``async with httpx.AsyncClient(...)`` block picks up the mock.
"""

from unittest.mock import patch

import httpx
import pytest

from helprs.core.exceptions import (
    ExternalServiceError,
    NotFoundError,
    RateLimitExceededError,
)
from helprs.modules.comprehension.infrastructure import github_diff
from helprs.modules.comprehension.infrastructure.github_diff import fetch_pr_diff


def _client_factory(handler):
    """Return a patched ``httpx.AsyncClient`` class that uses ``MockTransport``."""
    transport = httpx.MockTransport(handler)

    class PatchedClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    return PatchedClient


class TestHappyPath:
    async def test_returns_small_body_verbatim(self):
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            captured["accept"] = request.headers.get("Accept")
            captured["auth"] = request.headers.get("Authorization")
            return httpx.Response(200, text="diff --git a/f b/f\n+new line")

        with patch.object(github_diff.httpx, "AsyncClient", _client_factory(handler)):
            result = await fetch_pr_diff(
                owner="acme",
                repo="repo",
                pr_number=42,
                installation_token="ghs_abc",
            )

        assert result == "diff --git a/f b/f\n+new line"
        assert captured["url"] == "https://api.github.com/repos/acme/repo/pulls/42"
        assert captured["accept"] == "application/vnd.github.v3.diff"
        assert captured["auth"] == "Bearer ghs_abc"

    async def test_large_body_is_truncated_with_marker(self):
        big_body = "x" * (1_200_000)

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=big_body)

        with patch.object(github_diff.httpx, "AsyncClient", _client_factory(handler)):
            result = await fetch_pr_diff(
                owner="acme",
                repo="repo",
                pr_number=42,
                installation_token="ghs_abc",
            )

        assert "<!-- truncated: diff exceeded 1 MB -->" in result
        assert result.startswith("x")

        # Hard cap: total returned bytes must never exceed _MAX_DIFF_BYTES.
        assert len(result.encode("utf-8")) <= github_diff._MAX_DIFF_BYTES

        # The body fills exactly _BODY_BYTE_BUDGET bytes of 'x'; the
        # marker begins with "\n\n<!--", so the literal "<!-- truncated"
        # substring appears at index BUDGET + 2.
        marker_index = result.index("<!-- truncated")
        assert marker_index == github_diff._BODY_BYTE_BUDGET + 2


class TestErrorPaths:
    async def test_404_raises_not_found(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, text="not found")

        with (
            patch.object(github_diff.httpx, "AsyncClient", _client_factory(handler)),
            pytest.raises(NotFoundError),
        ):
            await fetch_pr_diff(
                owner="acme",
                repo="repo",
                pr_number=99999,
                installation_token="ghs_abc",
            )

    async def test_500_raises_external_service_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="boom")

        with (
            patch.object(github_diff.httpx, "AsyncClient", _client_factory(handler)),
            pytest.raises(ExternalServiceError),
        ):
            await fetch_pr_diff(
                owner="acme",
                repo="repo",
                pr_number=42,
                installation_token="ghs_abc",
            )

    async def test_timeout_raises_external_service_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.TimeoutException("timed out", request=request)

        with (
            patch.object(github_diff.httpx, "AsyncClient", _client_factory(handler)),
            pytest.raises(ExternalServiceError),
        ):
            await fetch_pr_diff(
                owner="acme",
                repo="repo",
                pr_number=42,
                installation_token="ghs_abc",
            )

    async def test_403_raises_external_service_error(self):
        """Non-404/429 client errors bubble as ExternalServiceError."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(403, text="forbidden")

        with (
            patch.object(github_diff.httpx, "AsyncClient", _client_factory(handler)),
            pytest.raises(ExternalServiceError),
        ):
            await fetch_pr_diff(
                owner="acme",
                repo="repo",
                pr_number=42,
                installation_token="ghs_abc",
            )

    async def test_429_raises_rate_limit_exceeded(self):
        """GitHub primary rate limit maps to RateLimitExceededError (HTTP 429)."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, text="rate limited")

        with (
            patch.object(github_diff.httpx, "AsyncClient", _client_factory(handler)),
            pytest.raises(RateLimitExceededError),
        ):
            await fetch_pr_diff(
                owner="acme",
                repo="repo",
                pr_number=42,
                installation_token="ghs_abc",
            )

    async def test_connect_error_raises_external_service_error(self):
        """DNS/TLS/socket failures map to ExternalServiceError (not 500)."""

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("dns lookup failed", request=request)

        with (
            patch.object(github_diff.httpx, "AsyncClient", _client_factory(handler)),
            pytest.raises(ExternalServiceError),
        ):
            await fetch_pr_diff(
                owner="acme",
                repo="repo",
                pr_number=42,
                installation_token="ghs_abc",
            )

    async def test_http_error_scrubs_bearer_token_from_request_headers(self):
        """HTTPStatusError path must redact the Authorization header so
        structured loggers capturing ``e.request.headers`` cannot leak
        the installation token.
        """
        captured_error: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="boom")

        with patch.object(github_diff.httpx, "AsyncClient", _client_factory(handler)):
            try:
                await fetch_pr_diff(
                    owner="acme",
                    repo="repo",
                    pr_number=42,
                    installation_token="ghs_super_secret",
                )
            except ExternalServiceError as e:
                captured_error["cause"] = e.__cause__

        cause = captured_error.get("cause")
        assert isinstance(cause, httpx.HTTPStatusError)
        auth = cause.request.headers.get("authorization", "")
        assert "ghs_super_secret" not in auth
        assert "<redacted>" in auth


class TestUrlEncoding:
    async def test_owner_and_repo_are_url_encoded(self):
        """Defense-in-depth: any ``/`` or special char in owner/repo
        must be percent-encoded so a corrupted row cannot rewrite the
        GitHub API path.
        """
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            return httpx.Response(200, text="ok")

        with patch.object(github_diff.httpx, "AsyncClient", _client_factory(handler)):
            await fetch_pr_diff(
                owner="ac/me",
                repo="re po",
                pr_number=1,
                installation_token="ghs_abc",
            )

        assert captured["url"] == "https://api.github.com/repos/ac%2Fme/re%20po/pulls/1"
