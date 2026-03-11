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
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing_int = {c["name"] for c in inspector.get_columns("integrations")}
    if "sync_error_count" not in existing_int:
        op.add_column(
            "integrations",
            sa.Column("sync_error_count", sa.Integer(), nullable=False, server_default="0"),
        )

    existing_apr = {c["name"] for c in inspector.get_columns("approvals")}
    if "expires_at" not in existing_apr:
        op.add_column(
            "approvals",
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        )

    existing_idxs = {i["name"] for i in inspector.get_indexes("approvals")}
    if "ix_approvals_expires_at" not in existing_idxs:
        op.create_index("ix_approvals_expires_at", "approvals", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_approvals_expires_at", table_name="approvals")
    op.drop_column("approvals", "expires_at")
    op.drop_column("integrations", "sync_error_count")
