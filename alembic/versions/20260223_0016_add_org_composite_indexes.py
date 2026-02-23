"""add composite org indexes for hot-path tenant-scoped queries

Revision ID: 20260223_0016
Revises: 20260223_0015
Create Date: 2026-02-23
"""

from alembic import op
import sqlalchemy as sa


revision = "20260223_0016"
down_revision = "20260223_0015"
branch_labels = None
depends_on = None


def _has_index(inspector: sa.Inspector, table: str, index_name: str) -> bool:
    return any(idx["name"] == index_name for idx in inspector.get_indexes(table))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "ai_call_logs" in tables and not _has_index(inspector, "ai_call_logs", "ix_ai_call_logs_org_created"):
        op.create_index(
            "ix_ai_call_logs_org_created",
            "ai_call_logs",
            ["organization_id", "created_at"],
            unique=False,
        )

    if "decision_traces" in tables and not _has_index(inspector, "decision_traces", "ix_decision_traces_org_created"):
        op.create_index(
            "ix_decision_traces_org_created",
            "decision_traces",
            ["organization_id", "created_at"],
            unique=False,
        )

    if "approvals" in tables and not _has_index(inspector, "approvals", "ix_approvals_org_status_created"):
        op.create_index(
            "ix_approvals_org_status_created",
            "approvals",
            ["organization_id", "status", "created_at"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "approvals" in tables and _has_index(inspector, "approvals", "ix_approvals_org_status_created"):
        op.drop_index("ix_approvals_org_status_created", table_name="approvals")

    if "decision_traces" in tables and _has_index(inspector, "decision_traces", "ix_decision_traces_org_created"):
        op.drop_index("ix_decision_traces_org_created", table_name="decision_traces")

    if "ai_call_logs" in tables and _has_index(inspector, "ai_call_logs", "ix_ai_call_logs_org_created"):
        op.drop_index("ix_ai_call_logs_org_created", table_name="ai_call_logs")
