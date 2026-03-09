"""add persistent job queue table

Revision ID: 20260309_0085
Revises: 20260307_0084
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260309_0085"
down_revision: str | None = "20260307_0084"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "job_queue",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("job_name", sa.String(120), nullable=False, index=True),
        sa.Column("payload_json", sa.Text, nullable=False, server_default="{}"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending", index=True),
        sa.Column("priority", sa.Integer, nullable=False, server_default="0"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("max_retries", sa.Integer, nullable=False, server_default="3"),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("run_after", sa.DateTime(timezone=True), server_default=sa.func.now(), index=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.String(80), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    # Composite index for worker claim query
    op.create_index(
        "ix_job_queue_pending_runnable",
        "job_queue",
        ["status", "run_after", "priority"],
    )


def downgrade() -> None:
    op.drop_index("ix_job_queue_pending_runnable", table_name="job_queue")
    op.drop_table("job_queue")
