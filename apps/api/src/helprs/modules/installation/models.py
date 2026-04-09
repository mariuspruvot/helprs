"""Installation ORM models."""

import uuid
from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from helprs.core.database import Base


class Installation(Base):
    """GitHub App installation record."""

    __tablename__ = "installations"

    github_installation_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, index=True, nullable=False
    )
    account_login: Mapped[str] = mapped_column(String(255), nullable=False)
    account_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    account_type: Mapped[str] = mapped_column(String(50), nullable=False)
    repository_selection: Mapped[str] = mapped_column(String(20), nullable=False)
    app_slug: Mapped[str] = mapped_column(String(255), nullable=False)
    target_type: Mapped[str] = mapped_column(String(50), nullable=False)
    permissions: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    events: Mapped[list | None] = mapped_column(JSON, nullable=True)
    suppression_labels: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    suspended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    byok_config: Mapped["BYOKConfig | None"] = relationship(
        "BYOKConfig", back_populates="installation", uselist=False
    )


class BYOKConfig(Base):
    """BYOK (Bring Your Own Key) configuration for an installation."""

    __tablename__ = "byok_configs"

    installation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("installations.id"), unique=True, index=True, nullable=False
    )
    encrypted_api_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    key_status: Mapped[str] = mapped_column(String(20), default="valid")
    validated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    key_hint: Mapped[str | None] = mapped_column(String(20), nullable=True)

    installation: Mapped["Installation"] = relationship(
        "Installation", back_populates="byok_config"
    )
