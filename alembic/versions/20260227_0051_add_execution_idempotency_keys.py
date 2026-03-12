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
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing_apr = {c["name"] for c in inspector.get_columns("approvals")}
    if "request_idempotency_key" not in existing_apr:
        op.add_column("approvals", sa.Column("request_idempotency_key", sa.String(length=128), nullable=True))

    existing_exe = {c["name"] for c in inspector.get_columns("executions")}
    if "execute_idempotency_key" not in existing_exe:
        op.add_column("executions", sa.Column("execute_idempotency_key", sa.String(length=128), nullable=True))

    existing_apr_idxs = {i["name"] for i in inspector.get_indexes("approvals")}
    if "ix_approvals_org_request_idempotency_key" not in existing_apr_idxs:
        op.create_index(
            "ix_approvals_org_request_idempotency_key",
            "approvals",
            ["organization_id", "request_idempotency_key"],
            unique=True,
        )

    existing_exe_idxs = {i["name"] for i in inspector.get_indexes("executions")}
    if "ix_executions_org_execute_idempotency_key" not in existing_exe_idxs:
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
