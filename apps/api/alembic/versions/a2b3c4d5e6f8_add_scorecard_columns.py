"""Add scorecard and xp_earned columns to container_sessions.

Revision ID: a2b3c4d5e6f8
Revises: a1b2c3d4e5f7
Create Date: 2026-04-20
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a2b3c4d5e6f8"
down_revision: str | None = "a1b2c3d4e5f7"
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None


def upgrade() -> None:
    op.add_column("container_sessions", sa.Column("scorecard", postgresql.JSONB(), nullable=True))
    op.add_column("container_sessions", sa.Column("xp_earned", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("container_sessions", "xp_earned")
    op.drop_column("container_sessions", "scorecard")
