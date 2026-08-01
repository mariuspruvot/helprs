"""Normalize container_sessions.status to enum values, not member names.

Without ``values_callable`` on the Enum type, SQLAlchemy persisted the member
NAME ("RUNNING") while the column's server_default is the value ("pending")
and the API returns the value. Rows written by the ORM and rows written by the
database default therefore disagreed, and reading a value-cased row through
the ORM raised ``LookupError``.

The model now maps by value; this migration brings existing rows in line. Only
rows written by the ORM need changing, and every enum member is lower-case
with no internal case distinctions, so ``lower()`` is exactly the mapping.

Revision ID: c4d5e6f7a0b1
Revises: b3c4d5e6f9a0
Create Date: 2026-08-01

"""

from collections.abc import Sequence

from alembic import op

revision: str = "c4d5e6f7a0b1"
down_revision: str | None = "b3c4d5e6f9a0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("UPDATE container_sessions SET status = lower(status) WHERE status <> lower(status)")


def downgrade() -> None:
    op.execute("UPDATE container_sessions SET status = upper(status) WHERE status <> upper(status)")
