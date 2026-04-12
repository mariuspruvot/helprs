"""add scores table

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-04-12 12:00:00.000000

Story 4.1: introduces the ``scores`` table (metadata-only — no verbatim
Q&A text; see FR35/NFR14). One score per session, storing four dimension
scores (0-10), a verdict string, and a JSONB gap summary.

Check constraints enforce 0-10 range on each dimension at the DB level.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: str | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scores",
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("depth", sa.Integer(), nullable=False),
        sa.Column("accuracy", sa.Integer(), nullable=False),
        sa.Column("completeness", sa.Integer(), nullable=False),
        sa.Column("insight", sa.Integer(), nullable=False),
        sa.Column("verdict", sa.String(length=20), nullable=False),
        sa.Column("gap_summary", postgresql.JSONB(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", name="uq_scores_session_id"),
        sa.CheckConstraint("depth >= 0 AND depth <= 10", name="ck_scores_depth_range"),
        sa.CheckConstraint("accuracy >= 0 AND accuracy <= 10", name="ck_scores_accuracy_range"),
        sa.CheckConstraint("completeness >= 0 AND completeness <= 10", name="ck_scores_completeness_range"),
        sa.CheckConstraint("insight >= 0 AND insight <= 10", name="ck_scores_insight_range"),
    )


def downgrade() -> None:
    op.drop_table("scores")
