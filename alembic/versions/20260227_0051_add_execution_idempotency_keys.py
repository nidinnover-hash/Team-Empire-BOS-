"""add approval/execution idempotency keys

Revision ID: 20260227_0051
Revises: 20260227_0050
Create Date: 2026-02-27
"""
import sqlalchemy as sa

from alembic import op

revision = "20260227_0051"
down_revision = "20260227_0050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("approvals", sa.Column("request_idempotency_key", sa.String(length=128), nullable=True))
    op.add_column("executions", sa.Column("execute_idempotency_key", sa.String(length=128), nullable=True))

    op.create_index(
        "ix_approvals_org_request_idempotency_key",
        "approvals",
        ["organization_id", "request_idempotency_key"],
        unique=True,
    )
    op.create_index(
        "ix_executions_org_execute_idempotency_key",
        "executions",
        ["organization_id", "execute_idempotency_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_executions_org_execute_idempotency_key", table_name="executions")
    op.drop_index("ix_approvals_org_request_idempotency_key", table_name="approvals")
    op.drop_column("executions", "execute_idempotency_key")
    op.drop_column("approvals", "request_idempotency_key")
