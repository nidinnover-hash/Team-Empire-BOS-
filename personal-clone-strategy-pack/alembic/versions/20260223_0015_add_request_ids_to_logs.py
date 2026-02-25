"""add request_id columns to ai_call_logs and decision_traces

Revision ID: 20260223_0015
Revises: 20260223_0014
Create Date: 2026-02-23
"""

from alembic import op
import sqlalchemy as sa


revision = "20260223_0015"
down_revision = "20260223_0014"
branch_labels = None
depends_on = None


def _has_column(inspector: sa.Inspector, table: str, column: str) -> bool:
    return any(col["name"] == column for col in inspector.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "ai_call_logs" in tables and not _has_column(inspector, "ai_call_logs", "request_id"):
        op.add_column("ai_call_logs", sa.Column("request_id", sa.String(length=64), nullable=True))
        op.create_index("ix_ai_call_logs_request_id", "ai_call_logs", ["request_id"], unique=False)

    if "decision_traces" in tables and not _has_column(inspector, "decision_traces", "request_id"):
        op.add_column("decision_traces", sa.Column("request_id", sa.String(length=64), nullable=True))
        op.create_index("ix_decision_traces_request_id", "decision_traces", ["request_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "decision_traces" in tables and _has_column(inspector, "decision_traces", "request_id"):
        op.drop_index("ix_decision_traces_request_id", table_name="decision_traces")
        op.drop_column("decision_traces", "request_id")

    if "ai_call_logs" in tables and _has_column(inspector, "ai_call_logs", "request_id"):
        op.drop_index("ix_ai_call_logs_request_id", table_name="ai_call_logs")
        op.drop_column("ai_call_logs", "request_id")
