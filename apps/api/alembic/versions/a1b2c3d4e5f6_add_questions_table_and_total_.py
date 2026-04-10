"""add questions table and total_questions

Revision ID: a1b2c3d4e5f6
Revises: 9036c7377667
Create Date: 2026-04-10 14:00:00.000000

Story 3.3: introduces the ``questions`` table (metadata-only — no
``text`` column; see FR35/NFR14) and adds ``sessions.total_questions``
so the session detail endpoint + SSE stream know up-front how many
questions to ask. Existing rows get ``total_questions = 0`` via the
``server_default``.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "9036c7377667"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---- sessions.total_questions (additive, nullable=False + default) ----
    op.add_column(
        "sessions",
        sa.Column(
            "total_questions",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )

    # ---- questions table -------------------------------------------------
    op.create_table(
        "questions",
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("topic", sa.String(length=32), nullable=False),
        sa.Column("text_hash", sa.String(length=64), nullable=False),
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
        sa.UniqueConstraint(
            "session_id",
            "number",
            name="uq_questions_session_number",
        ),
    )
    op.create_index(
        "ix_questions_session_id",
        "questions",
        ["session_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_questions_session_id", table_name="questions")
    op.drop_table("questions")
    op.drop_column("sessions", "total_questions")
