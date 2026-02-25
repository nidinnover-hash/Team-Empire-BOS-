"""add daily task plans table

Revision ID: 20260221_0007
Revises: 20260221_0006
Create Date: 2026-02-21
"""

from alembic import op
import sqlalchemy as sa


revision = "20260221_0007"
down_revision = "20260221_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "daily_task_plans",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("team_member_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("tasks_json", sa.JSON(), nullable=False),        # list of task dicts
        sa.Column("ai_reasoning", sa.Text(), nullable=True),       # why these tasks
        sa.Column("status", sa.String(30), nullable=False, server_default="draft"),
        sa.Column("approved_by", sa.Integer(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["team_member_id"], ["team_members.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_daily_task_plans_date", "daily_task_plans", ["date"])
    op.create_index("ix_daily_task_plans_team_member_id", "daily_task_plans", ["team_member_id"])
    op.create_index("ix_daily_task_plans_status", "daily_task_plans", ["status"])
    op.create_index("ix_daily_task_plans_org_date", "daily_task_plans", ["organization_id", "date"])


def downgrade() -> None:
    op.drop_index("ix_daily_task_plans_org_date", table_name="daily_task_plans")
    op.drop_index("ix_daily_task_plans_status", table_name="daily_task_plans")
    op.drop_index("ix_daily_task_plans_team_member_id", table_name="daily_task_plans")
    op.drop_index("ix_daily_task_plans_date", table_name="daily_task_plans")
    op.drop_table("daily_task_plans")
