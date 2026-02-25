"""add daily runs table

Revision ID: 20260221_0009
Revises: 20260221_0008
Create Date: 2026-02-21
"""

from alembic import op
import sqlalchemy as sa


revision = "20260221_0009"
down_revision = "20260221_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "daily_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("run_date", sa.Date(), nullable=False),
        sa.Column("team_filter", sa.String(length=50), nullable=False, server_default="*"),
        sa.Column("requested_by", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="completed"),
        sa.Column("drafted_plan_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("drafted_email_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pending_approvals", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("result_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("organization_id", "run_date", "team_filter", name="uq_daily_runs_org_date_team"),
    )
    op.create_index("ix_daily_runs_organization_id", "daily_runs", ["organization_id"], unique=False)
    op.create_index("ix_daily_runs_run_date", "daily_runs", ["run_date"], unique=False)
    op.create_index("ix_daily_runs_team_filter", "daily_runs", ["team_filter"], unique=False)
    op.create_index("ix_daily_runs_requested_by", "daily_runs", ["requested_by"], unique=False)
    op.create_index("ix_daily_runs_status", "daily_runs", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_daily_runs_status", table_name="daily_runs")
    op.drop_index("ix_daily_runs_requested_by", table_name="daily_runs")
    op.drop_index("ix_daily_runs_team_filter", table_name="daily_runs")
    op.drop_index("ix_daily_runs_run_date", table_name="daily_runs")
    op.drop_index("ix_daily_runs_organization_id", table_name="daily_runs")
    op.drop_table("daily_runs")
