"""Tests for exception handling."""

import pytest
from httpx import ASGITransport, AsyncClient

from helprs.core.exceptions import (
    BYOKKeyInvalidError,
    ConflictError,
    DomainError,
    DomainValidationError,
    ExternalServiceError,
    ForbiddenError,
    NotFoundError,
    RateLimitExceededError,
    UnauthorizedError,
    domain_exception_handler,
)


@pytest.fixture
def exception_app():
    """Create a test app with domain exception handler and test routes."""
    from fastapi import FastAPI

    app = FastAPI()
    app.add_exception_handler(DomainError, domain_exception_handler)

    @app.get("/raise-not-found")
    async def raise_not_found():
        raise NotFoundError("Item not found")

    @app.get("/raise-conflict")
    async def raise_conflict():
        raise ConflictError("Already exists")

    @app.get("/raise-validation")
    async def raise_validation():
        raise DomainValidationError("Invalid input", detail={"field": "email"})

    @app.get("/raise-unauthorized")
    async def raise_unauthorized():
        raise UnauthorizedError()

    @app.get("/raise-forbidden")
    async def raise_forbidden():
        raise ForbiddenError()

    @app.get("/raise-byok")
    async def raise_byok():
        raise BYOKKeyInvalidError()

    @app.get("/raise-rate-limit")
    async def raise_rate_limit():
        raise RateLimitExceededError()

    @app.get("/raise-external")
    async def raise_external():
        raise ExternalServiceError("GitHub API unavailable")

    return app


@pytest.fixture
async def exc_client(exception_app):
    async with AsyncClient(transport=ASGITransport(app=exception_app), base_url="http://test") as ac:
        yield ac


EXCEPTION_CASES = [
    ("/raise-not-found", 404, "not_found", "Item not found", None),
    ("/raise-conflict", 409, "conflict", "Already exists", None),
    ("/raise-validation", 422, "validation_error", "Invalid input", {"field": "email"}),
    ("/raise-unauthorized", 401, "unauthorized", "Unauthorized", None),
    ("/raise-forbidden", 403, "forbidden", "Forbidden", None),
    ("/raise-byok", 400, "byok_key_invalid", "BYOK key is invalid", None),
    ("/raise-rate-limit", 429, "rate_limit_exceeded", "Rate limit exceeded", None),
    ("/raise-external", 502, "external_service_error", "GitHub API unavailable", None),
]


@pytest.mark.parametrize("path,status,error_code,message,detail", EXCEPTION_CASES)
async def test_exception_returns_correct_response(exc_client, path, status, error_code, message, detail):
    response = await exc_client.get(path)
    assert response.status_code == status
    body = response.json()
    assert body["error"] == error_code
    assert body["message"] == message
    assert body["detail"] == detail
