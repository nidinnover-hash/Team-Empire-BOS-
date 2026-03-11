"""Add clone_memory_entries table (requires workspaces from 0070).

Revision ID: 20260305_0070b
Revises: 20260305_0070
Create Date: 2026-03-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260305_0070b"
down_revision: str | None = "20260305_0070"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "clone_memory_entries" not in tables:
        op.create_table(
            "clone_memory_entries",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("organization_id", sa.Integer(), nullable=False),
            sa.Column("workspace_id", sa.Integer(), nullable=True),
            sa.Column("employee_id", sa.Integer(), nullable=False),
            sa.Column("situation", sa.Text(), nullable=False),
            sa.Column("action_taken", sa.Text(), nullable=False),
            sa.Column("outcome", sa.String(length=30), nullable=False),
            sa.Column("outcome_detail", sa.Text(), nullable=True),
            sa.Column("category", sa.String(length=40), nullable=False, server_default="general"),
            sa.Column("tags", sa.String(length=500), nullable=True),
            sa.Column("confidence", sa.Float(), nullable=False, server_default="0.7"),
            sa.Column("reinforcement_count", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("last_retrieved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("source_type", sa.String(length=30), nullable=True),
            sa.Column("source_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_clone_memory_entries_organization_id", "clone_memory_entries", ["organization_id"])
        op.create_index("ix_clone_memory_entries_workspace_id", "clone_memory_entries", ["workspace_id"])
        op.create_index("ix_clone_memory_entries_employee_id", "clone_memory_entries", ["employee_id"])

    # Also add the CHECK constraints that 0061 skipped (table didn't exist then)
    existing_ck = {
        row[0] for row in bind.execute(
            sa.text("SELECT conname FROM pg_constraint WHERE contype = 'c'")
        ).fetchall()
    }
    if "ck_clone_memory_outcome" not in existing_ck:
        op.create_check_constraint(
            "ck_clone_memory_outcome",
            "clone_memory_entries",
            "outcome IN ('success', 'partial', 'failure')",
        )
    if "ck_clone_memory_category" not in existing_ck:
        op.create_check_constraint(
            "ck_clone_memory_category",
            "clone_memory_entries",
            "category IN ('sales', 'support', 'operations', 'onboarding', 'negotiation', 'general')",
        )


def downgrade() -> None:
    op.drop_table("clone_memory_entries")
