"""Add token_version to github_users.

Refresh tokens are JWTs, so they cannot be withdrawn once issued. Each one
now carries the version it was minted under, and logout bumps this column --
invalidating every outstanding token for that user without storing anything
per token or needing a job to expire it.

Existing rows default to 0. Tokens issued before this migration carry no
``ver`` claim and are rejected on their next refresh, logging current users
out once. That is the intent rather than a side effect: the point of the
change is that tokens minted under the old rules stop being honoured.

Revision ID: 5b500a24f018
Revises: c4d5e6f7a0b1
Create Date: 2026-08-01

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5b500a24f018"
down_revision: str | None = "c4d5e6f7a0b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("github_users", sa.Column("token_version", sa.Integer(), server_default="0", nullable=False))


def downgrade() -> None:
    op.drop_column("github_users", "token_version")
