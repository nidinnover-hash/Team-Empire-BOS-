"""add executions table

Revision ID: 20260221_0003
Revises: 20260221_0002
Create Date: 2026-02-21
"""

from alembic import op
import sqlalchemy as sa


revision = "20260221_0003"
down_revision = "20260221_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "executions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("approval_id", sa.Integer(), nullable=False),
        sa.Column("triggered_by", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("output_json", sa.JSON(), nullable=False),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["approval_id"], ["approvals.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_executions_organization_id", "executions", ["organization_id"], unique=False)
    op.create_index("ix_executions_approval_id", "executions", ["approval_id"], unique=False)
    op.create_index("ix_executions_triggered_by", "executions", ["triggered_by"], unique=False)
    op.create_index("ix_executions_status", "executions", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_executions_status", table_name="executions")
    op.drop_index("ix_executions_triggered_by", table_name="executions")
    op.drop_index("ix_executions_approval_id", table_name="executions")
    op.drop_index("ix_executions_organization_id", table_name="executions")
    op.drop_table("executions")
