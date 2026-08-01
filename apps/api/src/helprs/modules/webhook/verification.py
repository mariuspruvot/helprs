"""Webhook signature verification dependency."""

import structlog
from fastapi import Request

from helprs.core.config import get_settings
from helprs.core.exceptions import UnauthorizedError
from helprs.core.security import verify_github_webhook_signature

logger = structlog.get_logger()


async def verify_webhook_signature(request: Request) -> bytes:
    """FastAPI dependency that verifies GitHub webhook HMAC signature.

    Returns the raw request body on success for downstream parsing.
    Raises UnauthorizedError on failure.
    """
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")
    settings = get_settings()

    if not settings.GITHUB_WEBHOOK_SECRET:
        await logger.aerror("webhook_secret_not_configured")
        raise UnauthorizedError("Webhook signature verification is not configured")

    if not verify_github_webhook_signature(body, signature, settings.GITHUB_WEBHOOK_SECRET.get_secret_value()):
        await logger.awarning(
            "webhook_signature_invalid",
            has_signature=signature is not None,
        )
        raise UnauthorizedError("Invalid webhook signature")

    return body
