"""Add composite indexes for automation-heavy query paths.

Revision ID: 20260301_0056
Revises: 20260301_0055
Create Date: 2026-03-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260301_0056"
down_revision = "20260301_0055"
branch_labels = None
depends_on = None


def _has_index(bind: sa.Connection, index_name: str) -> bool:
    dialect = bind.dialect.name
    if dialect == "sqlite":
        rows = bind.execute(
            sa.text(
                "SELECT name FROM sqlite_master WHERE type='index' AND name=:n"
            ),
            {"n": index_name},
        ).fetchall()
        return len(rows) > 0
    rows = bind.execute(
        sa.text("SELECT 1 FROM pg_indexes WHERE indexname = :n"),
        {"n": index_name},
    ).fetchall()
    return len(rows) > 0


def upgrade() -> None:
    bind = op.get_bind()

    idx = "ix_webhook_deliveries_status_retry_created"
    if not _has_index(bind, idx):
        op.create_index(
            idx,
            "webhook_deliveries",
            ["status", "next_retry_at", "created_at"],
            unique=False,
        )

    idx = "ix_scheduler_job_runs_org_started"
    if not _has_index(bind, idx):
        op.create_index(
            idx,
            "scheduler_job_runs",
            ["organization_id", "started_at"],
            unique=False,
        )

    idx = "ix_daily_runs_org_created"
    if not _has_index(bind, idx):
        op.create_index(
            idx,
            "daily_runs",
            ["organization_id", "created_at"],
            unique=False,
        )

    idx = "ix_self_learning_runs_org_status_week"
    if not _has_index(bind, idx):
        op.create_index(
            idx,
            "self_learning_runs",
            ["organization_id", "status", "week_start_date"],
            unique=False,
        )


def downgrade() -> None:
    op.drop_index(
        "ix_self_learning_runs_org_status_week",
        table_name="self_learning_runs",
    )
    op.drop_index(
        "ix_daily_runs_org_created",
        table_name="daily_runs",
    )
    op.drop_index(
        "ix_scheduler_job_runs_org_started",
        table_name="scheduler_job_runs",
    )
    op.drop_index(
        "ix_webhook_deliveries_status_retry_created",
        table_name="webhook_deliveries",
    )
