"""Webhook use cases.

This module exists because the router used to *be* the use case: one handler
did header validation, JSON decoding, type-guarding, field extraction, log
binding, persistence and task scheduling, then returned an untyped dict. The
webhook module was the only one in the codebase without a service layer.
"""

import json

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from helprs.core.exceptions import DomainValidationError
from helprs.modules.webhook import repository
from helprs.modules.webhook.models import WebhookEvent
from helprs.modules.webhook.repository import DuplicateWebhookError
from helprs.modules.webhook.schemas import WebhookDelivery

logger = structlog.get_logger()


def parse_delivery(*, delivery_id: str, event_type: str, body: bytes) -> WebhookDelivery:
    """Turn the raw request into a validated delivery.

    Raises ``DomainValidationError`` -- a 400 -- for anything malformed, so
    the caller never has to inspect the raw body itself.
    """
    if not delivery_id.strip():
        raise DomainValidationError("X-GitHub-Delivery header is required")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as e:
        raise DomainValidationError("Invalid JSON payload") from e
    if not isinstance(payload, dict):
        raise DomainValidationError("JSON payload must be an object")

    installation = payload.get("installation")
    github_installation_id = installation.get("id") if isinstance(installation, dict) else None
    action = payload.get("action")

    return WebhookDelivery(
        delivery_id=delivery_id.strip(),
        event_type=event_type,
        action=action if isinstance(action, str) else None,
        github_installation_id=github_installation_id if isinstance(github_installation_id, int) else None,
        payload=payload,
    )


async def record_delivery(session: AsyncSession, delivery: WebhookDelivery) -> WebhookEvent | None:
    """Persist a delivery, or return ``None`` if GitHub already sent it.

    GitHub retries deliveries, so a duplicate is an expected outcome rather
    than an error: the unique index on ``delivery_id`` is what makes the
    receiver idempotent.
    """
    try:
        return await repository.create_event(
            session,
            delivery_id=delivery.delivery_id,
            event_type=delivery.event_type,
            action=delivery.action,
            github_installation_id=delivery.github_installation_id,
            payload=delivery.payload,
        )
    except DuplicateWebhookError:
        await logger.ainfo("webhook_event_duplicate")
        return None
