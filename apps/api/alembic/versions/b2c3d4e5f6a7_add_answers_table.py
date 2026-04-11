"""add answers table

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-04-11 10:00:00.000000

Story 3.4: introduces the ``answers`` table (metadata-only — no
``text`` column; see FR35/NFR14). Mirror of ``questions`` from Story
3.3: only the SHA-256 ``text_hash`` and the ``latency_ms`` observability
hook are persisted alongside the standard ``id`` / ``created_at`` /
``updated_at`` columns from ``Base``.

The ``UniqueConstraint`` on ``question_id`` enforces "exactly one
answer per question" at the DB level. No separate single-column
``ix_answers_question_id`` index is created — the unique constraint
already builds a B-tree on the column (mirror of Story 3-3's
``questions`` table decision, P14).
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "answers",
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("text_hash", sa.String(length=64), nullable=False),
        sa.Column("latency_ms", sa.BigInteger(), nullable=False),
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
            ["question_id"],
            ["questions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "question_id",
            name="uq_answers_question_id",
        ),
    )


def downgrade() -> None:
    op.drop_table("answers")
