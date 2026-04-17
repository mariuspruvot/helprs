"""add container_sessions table

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-04-17 12:00:00.000000

Container orchestrator module: tracks ephemeral Docker containers
running Claude Code CLI skills against pull requests.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5f6a7b8c9d0"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "container_sessions",
        sa.Column("installation_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("pr_number", sa.Integer(), nullable=False),
        sa.Column("repo_full_name", sa.String(length=255), nullable=False),
        sa.Column("skill_name", sa.String(length=100), nullable=False),
        sa.Column("container_id", sa.String(length=128), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["installation_id"], ["installations.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["github_users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_container_sessions_installation_id"), "container_sessions", ["installation_id"])
    op.create_index(op.f("ix_container_sessions_user_id"), "container_sessions", ["user_id"])
    op.create_index(op.f("ix_container_sessions_repo_full_name"), "container_sessions", ["repo_full_name"])
    op.create_index(op.f("ix_container_sessions_status"), "container_sessions", ["status"])


def downgrade() -> None:
    op.drop_index(op.f("ix_container_sessions_status"), table_name="container_sessions")
    op.drop_index(op.f("ix_container_sessions_repo_full_name"), table_name="container_sessions")
    op.drop_index(op.f("ix_container_sessions_user_id"), table_name="container_sessions")
    op.drop_index(op.f("ix_container_sessions_installation_id"), table_name="container_sessions")
    op.drop_table("container_sessions")
