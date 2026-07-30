"""Drop pre-pivot comprehension tables.

The comprehension module was removed by the container pivot (ADR-001), but its
tables were never dropped: ``alembic upgrade head`` built a 12-table schema
while ``Base.metadata.create_all`` (used by the test fixtures) built a 6-table
one, and the next ``--autogenerate`` run would have emitted these drops on its
own. Downgrade is intentionally not supported — the rows are gone and the
models no longer exist.

Revision ID: b3c4d5e6f9a0
Revises: a2b3c4d5e6f8
"""

from collections.abc import Sequence

from alembic import op

revision: str = "b3c4d5e6f9a0"
down_revision: str | None = "a2b3c4d5e6f8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Child-to-parent order: answers and scores reference questions, which
# references sessions.
_DROPPED_TABLES = (
    "session_feedback",
    "question_reports",
    "scores",
    "answers",
    "questions",
    "sessions",
)


def upgrade() -> None:
    for table in _DROPPED_TABLES:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")


def downgrade() -> None:
    raise NotImplementedError("Pre-pivot tables cannot be restored; their models were removed in ADR-001.")
