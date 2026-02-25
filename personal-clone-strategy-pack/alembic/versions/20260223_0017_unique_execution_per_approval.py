"""add unique index on executions(approval_id) to prevent duplicate executions

Revision ID: 20260223_0017
Revises: 20260223_0016
Create Date: 2026-02-23
"""

from alembic import op

revision = "20260223_0017"
down_revision = "20260223_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "uq_execution_approval",
        "executions",
        ["approval_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_execution_approval", table_name="executions")
