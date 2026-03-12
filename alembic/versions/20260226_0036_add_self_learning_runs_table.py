"""add self_learning_runs table for weekly training idempotency

Revision ID: 20260226_0036
Revises: 20260226_0035
Create Date: 2026-02-26 13:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260226_0036"
down_revision = "20260226_0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "self_learning_runs" in set(inspector.get_table_names()):
        return
    op.create_table(
        "self_learning_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("week_start_date", sa.Date(), nullable=False),
        sa.Column("requested_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="running"),
        # Keep JSON default in application layer for cross-dialect safety.
        sa.Column("details_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "week_start_date", name="uq_self_learning_org_week"),
    )
    op.create_index("ix_self_learning_runs_organization_id", "self_learning_runs", ["organization_id"])
    op.create_index("ix_self_learning_runs_week_start_date", "self_learning_runs", ["week_start_date"])
    op.create_index("ix_self_learning_runs_requested_by", "self_learning_runs", ["requested_by"])
    op.create_index("ix_self_learning_runs_status", "self_learning_runs", ["status"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "self_learning_runs" not in set(inspector.get_table_names()):
        return
    existing_idxs = {i["name"] for i in inspector.get_indexes("self_learning_runs")}
    if "ix_self_learning_runs_status" in existing_idxs:
        op.drop_index("ix_self_learning_runs_status", table_name="self_learning_runs")
    if "ix_self_learning_runs_requested_by" in existing_idxs:
        op.drop_index("ix_self_learning_runs_requested_by", table_name="self_learning_runs")
    if "ix_self_learning_runs_week_start_date" in existing_idxs:
        op.drop_index("ix_self_learning_runs_week_start_date", table_name="self_learning_runs")
    if "ix_self_learning_runs_organization_id" in existing_idxs:
        op.drop_index("ix_self_learning_runs_organization_id", table_name="self_learning_runs")
    op.drop_table("self_learning_runs")
