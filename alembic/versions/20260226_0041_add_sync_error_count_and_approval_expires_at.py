"""Add sync_error_count to integrations and expires_at to approvals.

Revision ID: 20260226_0041
Revises: 20260226_0040
Create Date: 2026-02-26
"""
import sqlalchemy as sa
from alembic import op

revision = "20260226_0041"
down_revision = "20260226_0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "integrations",
        sa.Column("sync_error_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "approvals",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_approvals_expires_at", "approvals", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_approvals_expires_at", table_name="approvals")
    op.drop_column("approvals", "expires_at")
    op.drop_column("integrations", "sync_error_count")
