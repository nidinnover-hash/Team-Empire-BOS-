"""Add clone performance weekly table.

Revision ID: 20260224_0026
Revises: 20260224_0025
Create Date: 2026-02-24 21:20:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260224_0026"
down_revision: str | None = "20260224_0025"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "clone_performance_weekly" not in tables:
        op.create_table(
            "clone_performance_weekly",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("organization_id", sa.Integer(), nullable=False),
            sa.Column("employee_id", sa.Integer(), nullable=False),
            sa.Column("week_start_date", sa.Date(), nullable=False),
            sa.Column("productivity_score", sa.Float(), nullable=False),
            sa.Column("quality_score", sa.Float(), nullable=False),
            sa.Column("collaboration_score", sa.Float(), nullable=False),
            sa.Column("learning_score", sa.Float(), nullable=False),
            sa.Column("overall_score", sa.Float(), nullable=False),
            sa.Column("readiness_level", sa.String(length=20), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("organization_id", "employee_id", "week_start_date", name="uq_clone_perf_week"),
        )
        op.create_index("ix_clone_performance_weekly_organization_id", "clone_performance_weekly", ["organization_id"], unique=False)
        op.create_index("ix_clone_performance_weekly_employee_id", "clone_performance_weekly", ["employee_id"], unique=False)
        op.create_index("ix_clone_performance_weekly_week_start_date", "clone_performance_weekly", ["week_start_date"], unique=False)
    else:
        existing = {i["name"] for i in inspector.get_indexes("clone_performance_weekly")}
        for idx, cols in [
            ("ix_clone_performance_weekly_organization_id", ["organization_id"]),
            ("ix_clone_performance_weekly_employee_id", ["employee_id"]),
            ("ix_clone_performance_weekly_week_start_date", ["week_start_date"]),
        ]:
            if idx not in existing:
                op.create_index(idx, "clone_performance_weekly", cols, unique=False)


def downgrade() -> None:
    op.drop_index("ix_clone_performance_weekly_week_start_date", table_name="clone_performance_weekly")
    op.drop_index("ix_clone_performance_weekly_employee_id", table_name="clone_performance_weekly")
    op.drop_index("ix_clone_performance_weekly_organization_id", table_name="clone_performance_weekly")
    op.drop_table("clone_performance_weekly")
