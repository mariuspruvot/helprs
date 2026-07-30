"""Webhook reception routes.

Pattern (AC #1): verify HMAC → persist raw event → return 200 → dispatch in
``BackgroundTasks``. DB persistence covers the post-200 crash window; the
lifespan replay job picks up anything left in ``pending``/``processing``.
"""

import json
from typing import Annotated

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, Request

from helprs.core.dependencies import DbSession
from helprs.core.exceptions import DomainValidationError
from helprs.core.middleware import limiter
from helprs.modules.webhook import repository
from helprs.modules.webhook.repository import DuplicateWebhookError
from helprs.modules.webhook.tasks import process_webhook_event
from helprs.modules.webhook.verification import verify_webhook_signature

logger = structlog.get_logger()

# The raw body, only after its HMAC signature checked out.
VerifiedWebhookBody = Annotated[bytes, Depends(verify_webhook_signature)]

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/github")
@limiter.limit("100/minute")
async def receive_github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    session: DbSession,
    body: VerifiedWebhookBody,
) -> dict[str, object]:
    """Receive GitHub webhooks.

    Verifies HMAC (via dependency), persists the raw event, and schedules
    background dispatch. Returns 200 as soon as persistence succeeds.
    """
    delivery_id = (request.headers.get("X-GitHub-Delivery") or "").strip()
    if not delivery_id:
        raise DomainValidationError("X-GitHub-Delivery header is required")

    event_type = request.headers.get("X-GitHub-Event", "")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as e:
        raise DomainValidationError("Invalid JSON payload") from e
    if not isinstance(payload, dict):
        raise DomainValidationError("JSON payload must be an object")

    action = payload.get("action")
    installation = payload.get("installation") or {}
    github_installation_id = installation.get("id") if isinstance(installation, dict) else None

    # Bind log context for the remainder of the request + downstream background
    # task. The request-logging middleware clears context at request end.
    structlog.contextvars.bind_contextvars(
        delivery_id=delivery_id,
        event_type=event_type,
        action=action,
        github_installation_id=github_installation_id,
    )

    try:
        event = await repository.create_event(
            session,
            delivery_id=delivery_id,
            event_type=event_type,
            action=action,
            github_installation_id=github_installation_id,
            payload=payload,
        )
    except DuplicateWebhookError:
        await logger.ainfo("webhook_event_duplicate")
        return {"status": "ok", "duplicate": True}

    # Pass the session_factory (app-state object), not the request session,
    # since the request session is closed before the background task runs.
    background_tasks.add_task(
        process_webhook_event,
        request.app.state.session_factory,
        event.id,
    )

    return {"status": "ok", "duplicate": False}
