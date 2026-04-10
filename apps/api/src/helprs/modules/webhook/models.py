"""Webhook event ORM models."""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from helprs.core.database import Base


class WebhookEvent(Base):
    """Persisted GitHub webhook event for durable dispatch and crash-replay.

    Status machine: pending → processing → processed|ignored|failed.
    On crash mid-flight, the lifespan replay job picks up rows still in
    pending/processing after a grace period.
    """

    __tablename__ = "webhook_events"

    # X-GitHub-Delivery header (UUID). Unique — enforces idempotency for
    # GitHub redeliveries (see Story 1.4 deferred item).
    delivery_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)

    # X-GitHub-Event header value (e.g. "pull_request", "installation").
    event_type: Mapped[str] = mapped_column(String(50), index=True, nullable=False)

    # Payload "action" field (e.g. "opened", "synchronize"). Optional — some
    # events have no action subtype.
    action: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Extracted from payload.installation.id when present; used for log
    # correlation and future per-installation queries.
    github_installation_id: Mapped[int | None] = mapped_column(BigInteger, index=True, nullable=True)

    # Raw parsed JSON payload. JSONB (not JSON) for indexable/queryable storage.
    # TODO(ops): add a periodic cleanup job for webhook_events older than 30 days — deferred
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # One of: pending, processing, processed, failed, ignored.
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True, nullable=False)

    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
