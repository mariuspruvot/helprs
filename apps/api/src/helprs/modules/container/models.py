"""Container session ORM models."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from helprs.core.database import Base


class ContainerStatus(enum.StrEnum):
    """Lifecycle states for an ephemeral container session."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    # A user pressed stop, or the API shut down: neither a success nor a
    # failure of the skill. The column is a plain VARCHAR with no CHECK
    # constraint, so adding a value needs no migration.
    CANCELLED = "cancelled"


class ContainerSession(Base):
    """Tracks an ephemeral Docker container running a skill against a PR."""

    __tablename__ = "container_sessions"

    installation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("installations.id"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("github_users.id"),
        nullable=True,
        index=True,
    )
    pr_number: Mapped[int] = mapped_column(Integer, nullable=False)
    repo_full_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    skill_name: Mapped[str] = mapped_column(String(100), nullable=False)
    container_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[ContainerStatus] = mapped_column(
        # values_callable is load-bearing: without it SQLAlchemy persists the
        # member NAME ("RUNNING"), while this column's server_default is the
        # value ("pending") and the API returns the value too. Any row created
        # without an explicit status -- the DB default, raw SQL, a bulk import
        # -- was then unreadable through the ORM:
        #   LookupError: 'running' is not among the defined enum values
        Enum(
            ContainerStatus,
            name="container_status",
            native_enum=False,
            length=20,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
        default=ContainerStatus.PENDING,
        index=True,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scorecard: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    xp_earned: Mapped[int | None] = mapped_column(Integer, nullable=True)


class SessionEvent(Base):
    """A single stream-json event persisted from a container session.

    Stores raw NDJSON events (assistant, system, user, result) as JSONB
    so completed sessions can be replayed from the database.
    """

    __tablename__ = "session_events"
    __table_args__ = (UniqueConstraint("session_id", "event_id", name="uq_session_events_session_event"),)

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("container_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_id: Mapped[int] = mapped_column(Integer, nullable=False)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False)
