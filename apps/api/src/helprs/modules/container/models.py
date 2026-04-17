"""Container session ORM models."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from helprs.core.database import Base


class ContainerStatus(enum.StrEnum):
    """Lifecycle states for an ephemeral container session."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


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
        Enum(ContainerStatus, name="container_status", native_enum=False, length=20),
        nullable=False,
        default=ContainerStatus.PENDING,
        index=True,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
