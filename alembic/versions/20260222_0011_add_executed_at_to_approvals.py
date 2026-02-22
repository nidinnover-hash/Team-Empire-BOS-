"""add executed_at to approvals

Revision ID: 20260222_0011
Revises: 20260222_0010
Create Date: 2026-02-22
"""

from alembic import op
import sqlalchemy as sa


revision = "20260222_0011"
down_revision = "20260222_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # executed_at: timestamp set when the approval's action is actually executed.
    # NULL means not yet executed. Used to prevent double-execution of the same
    # approval (e.g. sending the same email twice).
    op.add_column(
        "approvals",
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_approvals_executed_at", "approvals", ["executed_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_approvals_executed_at", table_name="approvals")
    op.drop_column("approvals", "executed_at")
