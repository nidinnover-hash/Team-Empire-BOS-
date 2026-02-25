"""Add scheduler job run logs table.

Revision ID: 0024
Revises: 0023
Create Date: 2026-02-24
"""

from alembic import op
import sqlalchemy as sa

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scheduler_job_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("job_name", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("details_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("error", sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_scheduler_job_runs_org_id", "scheduler_job_runs", ["organization_id"])
    op.create_index("ix_scheduler_job_runs_job_name", "scheduler_job_runs", ["job_name"])
    op.create_index("ix_scheduler_job_runs_status", "scheduler_job_runs", ["status"])
    op.create_index("ix_scheduler_job_runs_started_at", "scheduler_job_runs", ["started_at"])
    op.create_index("ix_scheduler_job_runs_finished_at", "scheduler_job_runs", ["finished_at"])
    op.create_index(
        "ix_scheduler_job_runs_org_job_started",
        "scheduler_job_runs",
        ["organization_id", "job_name", "started_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_scheduler_job_runs_org_job_started", table_name="scheduler_job_runs")
    op.drop_index("ix_scheduler_job_runs_finished_at", table_name="scheduler_job_runs")
    op.drop_index("ix_scheduler_job_runs_started_at", table_name="scheduler_job_runs")
    op.drop_index("ix_scheduler_job_runs_status", table_name="scheduler_job_runs")
    op.drop_index("ix_scheduler_job_runs_job_name", table_name="scheduler_job_runs")
    op.drop_index("ix_scheduler_job_runs_org_id", table_name="scheduler_job_runs")
    op.drop_table("scheduler_job_runs")
