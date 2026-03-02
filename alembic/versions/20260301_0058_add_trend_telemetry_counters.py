"""Add trend telemetry counters table.

Revision ID: 20260301_0058
Revises: 20260301_0057
Create Date: 2026-03-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260301_0058"
down_revision = "20260301_0057"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trend_telemetry_counters",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("metric_name", sa.String(length=80), nullable=False),
        sa.Column("metric_value", sa.Float(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("organization_id", "metric_name", name="uq_trend_telemetry_counters_org_metric"),
    )
    op.create_index(
        "ix_trend_telemetry_counters_organization_id",
        "trend_telemetry_counters",
        ["organization_id"],
    )
    op.create_index(
        "ix_trend_telemetry_counters_metric_name",
        "trend_telemetry_counters",
        ["metric_name"],
    )
    op.create_index(
        "ix_trend_telemetry_counters_updated_at",
        "trend_telemetry_counters",
        ["updated_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_trend_telemetry_counters_updated_at", table_name="trend_telemetry_counters")
    op.drop_index("ix_trend_telemetry_counters_metric_name", table_name="trend_telemetry_counters")
    op.drop_index("ix_trend_telemetry_counters_organization_id", table_name="trend_telemetry_counters")
    op.drop_table("trend_telemetry_counters")
