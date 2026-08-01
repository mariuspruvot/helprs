"""Tests for CORS and rate limiting middleware."""

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from slowapi import Limiter
from slowapi.util import get_remote_address

import helprs.core.middleware as mw
from helprs.core.exceptions import DomainError, domain_exception_handler
from helprs.core.middleware import setup_middleware


class SettingsDouble:
    """The only field setup_middleware reads off Settings."""

    def __init__(self, cors_origins: list[str]) -> None:
        self.CORS_ORIGINS = cors_origins


def _create_test_app(cors_origins: list[str] | None = None) -> tuple[FastAPI, Limiter]:
    """Create a test app with middleware configured and a fresh limiter."""
    # Swap the module-level limiter for a fresh one so counters don't leak
    # between tests; setup_middleware reads it at call time.
    fresh_limiter = Limiter(key_func=get_remote_address)
    original_limiter = mw.limiter
    mw.limiter = fresh_limiter

    settings = SettingsDouble(cors_origins or ["http://localhost:5173"])

    app = FastAPI()
    app.add_exception_handler(DomainError, domain_exception_handler)
    setup_middleware(app, settings)

    @app.get("/test")
    async def test_endpoint():
        return {"ok": True}

    @app.get("/rate-limited")
    @fresh_limiter.limit("2/minute")
    async def rate_limited_endpoint(request: Request):
        return {"ok": True}

    # Restore original limiter after app setup (the app already has reference to fresh one)
    mw.limiter = original_limiter

    return app, fresh_limiter


@pytest.fixture
async def middleware_client():
    app, _ = _create_test_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


async def test_cors_allows_configured_origin():
    app, _ = _create_test_app(cors_origins=["http://localhost:5173"])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.options(
            "/test",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"


async def test_cors_rejects_non_allowed_origin():
    app, _ = _create_test_app(cors_origins=["http://localhost:5173"])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.options(
            "/test",
            headers={
                "Origin": "http://evil.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert "access-control-allow-origin" not in response.headers


async def test_rate_limit_returns_429_after_threshold():
    app, _ = _create_test_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # First 2 requests should pass
        for _ in range(2):
            resp = await client.get("/rate-limited")
            assert resp.status_code == 200

        # Third request should be rate limited
        resp = await client.get("/rate-limited")
        assert resp.status_code == 429


async def test_request_id_header_set(middleware_client):
    response = await middleware_client.get("/test")
    assert response.status_code == 200
    assert "x-request-id" in response.headers


async def test_rate_limited_response_carries_cors_headers():
    """A 429 must reach the browser as a 429, not as an opaque CORS failure.

    This holds today regardless of registration order, because slowapi's
    RateLimitExceeded subclasses HTTPException and is turned into a response
    by ExceptionMiddleware, which sits inside CORS. The test pins that down:
    if a future change makes the limiter short-circuit from a middleware
    outside CORS instead, the header disappears and this fails.
    """
    app, _ = _create_test_app(cors_origins=["http://localhost:5173"])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = {"Origin": "http://localhost:5173"}
        for _ in range(2):
            assert (await client.get("/rate-limited", headers=headers)).status_code == 200

        limited = await client.get("/rate-limited", headers=headers)

    assert limited.status_code == 429
    assert limited.headers.get("access-control-allow-origin") == "http://localhost:5173"


async def test_request_id_is_exposed_to_the_browser(middleware_client):
    """allow_headers only governs the request direction; without
    expose_headers the frontend cannot read the ID it would quote."""
    response = await middleware_client.get("/test", headers={"Origin": "http://localhost:5173"})
    exposed = response.headers.get("access-control-expose-headers", "")
    assert "X-Request-ID" in exposed
