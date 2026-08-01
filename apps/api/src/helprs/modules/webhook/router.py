"""Webhook reception routes.

Pattern (AC #1): verify HMAC → persist raw event → return 200 → dispatch in
``BackgroundTasks``. DB persistence covers the post-200 crash window; the
lifespan replay job picks up anything left in ``pending``/``processing``.
"""

from typing import Annotated

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, Request

from helprs.core.dependencies import DbSession
from helprs.core.middleware import limiter
from helprs.modules.webhook.schemas import WebhookAck
from helprs.modules.webhook.service import parse_delivery, record_delivery
from helprs.modules.webhook.tasks import process_webhook_event
from helprs.modules.webhook.verification import verify_webhook_signature

logger = structlog.get_logger()

# The raw body, only after its HMAC signature checked out.
VerifiedWebhookBody = Annotated[bytes, Depends(verify_webhook_signature)]

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/github", response_model=WebhookAck)
@limiter.limit("100/minute")
async def receive_github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    session: DbSession,
    body: VerifiedWebhookBody,
) -> WebhookAck:
    """Receive GitHub webhooks.

    The signature is already verified by the dependency that yields the body.
    This persists the delivery and schedules dispatch, returning 200 as soon
    as persistence succeeds -- the replay job covers the post-200 crash
    window.
    """
    delivery = parse_delivery(
        delivery_id=request.headers.get("X-GitHub-Delivery") or "",
        event_type=request.headers.get("X-GitHub-Event", ""),
        body=body,
    )

    # Bound for the rest of the request and the background task it schedules;
    # the request-logging middleware clears the context at request end.
    structlog.contextvars.bind_contextvars(
        delivery_id=delivery.delivery_id,
        event_type=delivery.event_type,
        action=delivery.action,
        github_installation_id=delivery.github_installation_id,
    )

    event = await record_delivery(session, delivery)
    if event is None:
        return WebhookAck(duplicate=True)

    # The session_factory from app state, not the request session: that one is
    # closed before the background task runs.
    background_tasks.add_task(process_webhook_event, request.app.state.session_factory, event.id)

    return WebhookAck(duplicate=False)
