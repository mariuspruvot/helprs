"""Comprehension SQLAlchemy ORM models.

``SessionModel`` is deliberately named with the ``Model`` suffix so it does
not shadow SQLAlchemy's ``Session`` / the domain ``Session`` entity. The
domain ↔ ORM mapping lives in ``repositories.py``.
"""

import uuid

from sqlalchemy import BigInteger, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from helprs.core.database import Base


class SessionModel(Base):
    """A single comprehension session — one side (author or reviewer) of a PR.

    Session pairs are keyed on ``(installation_id, repo_full_name, pr_number,
    role)``; the unique constraint enforces that exactly one row per role
    exists per PR. Story 3.1 will extend this model with question/answer
    links.
    """

    __tablename__ = "sessions"
    __table_args__ = (
        UniqueConstraint(
            "installation_id",
            "repo_full_name",
            "pr_number",
            "role",
            name="uq_sessions_installation_pr_role",
        ),
    )

    installation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("installations.id"),
        index=True,
        nullable=False,
    )
    github_installation_id: Mapped[int] = mapped_column(
        BigInteger,
        index=True,
        nullable=False,
    )
    repo_full_name: Mapped[str] = mapped_column(String(512), index=True, nullable=False)
    repo_owner: Mapped[str] = mapped_column(String(255), nullable=False)
    repo_name: Mapped[str] = mapped_column(String(255), nullable=False)
    pr_number: Mapped[int] = mapped_column(Integer, nullable=False)
    pr_title: Mapped[str] = mapped_column(String(1024), nullable=False)
    pr_head_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    pr_diff_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
