"""Webhook reception routes."""

import json

from fastapi import APIRouter, Depends, Request

from helprs.core.dependencies import DbSession
from helprs.core.middleware import limiter
from helprs.modules.webhook.dispatcher import dispatch_webhook
from helprs.modules.webhook.verification import verify_webhook_signature

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/github")
@limiter.limit("100/minute")
async def receive_github_webhook(
    request: Request,
    session: DbSession,
    body: bytes = Depends(verify_webhook_signature),  # noqa: B008
):
    """Receive GitHub webhooks. Verifies HMAC signature before processing."""
    event_type = request.headers.get("X-GitHub-Event", "")
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        from helprs.core.exceptions import DomainValidationError

        raise DomainValidationError("Invalid JSON payload") from e
    action = payload.get("action", "")

    await dispatch_webhook(event_type, action, payload, session)

    return {"status": "ok"}
