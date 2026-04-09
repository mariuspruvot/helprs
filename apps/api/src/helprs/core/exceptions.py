"""Application-level exception classes and handlers."""

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


class DomainError(Exception):
    """Base exception for all domain errors."""

    def __init__(
        self,
        error_code: str,
        message: str,
        http_status: int = 400,
        detail: Any = None,
    ):
        self.error_code = error_code
        self.message = message
        self.http_status = http_status
        self.detail = detail
        super().__init__(message)


class NotFoundError(DomainError):
    def __init__(self, message: str = "Resource not found", detail: Any = None):
        super().__init__("not_found", message, 404, detail)


class ConflictError(DomainError):
    def __init__(self, message: str = "Resource conflict", detail: Any = None):
        super().__init__("conflict", message, 409, detail)


class DomainValidationError(DomainError):
    def __init__(self, message: str = "Validation error", detail: Any = None):
        super().__init__("validation_error", message, 422, detail)


class UnauthorizedError(DomainError):
    def __init__(self, message: str = "Unauthorized", detail: Any = None):
        super().__init__("unauthorized", message, 401, detail)


class ForbiddenError(DomainError):
    def __init__(self, message: str = "Forbidden", detail: Any = None):
        super().__init__("forbidden", message, 403, detail)


class BYOKKeyInvalidError(DomainError):
    def __init__(self, message: str = "BYOK key is invalid", detail: Any = None):
        super().__init__("byok_key_invalid", message, 400, detail)


class RateLimitExceededError(DomainError):
    def __init__(self, message: str = "Rate limit exceeded", detail: Any = None):
        super().__init__("rate_limit_exceeded", message, 429, detail)


class ExternalServiceError(DomainError):
    def __init__(self, message: str = "External service error", detail: Any = None):
        super().__init__("external_service_error", message, 502, detail)


async def domain_exception_handler(request: Request, exc: DomainError) -> JSONResponse:
    """Global exception handler for DomainError subclasses."""
    return JSONResponse(
        status_code=exc.http_status,
        content={"error": exc.error_code, "message": exc.message, "detail": exc.detail},
    )
