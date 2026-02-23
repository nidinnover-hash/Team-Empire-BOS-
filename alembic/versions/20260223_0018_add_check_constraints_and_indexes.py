"""add check constraints on models, external_source index, ai_call_log org non-nullable

Revision ID: 20260223_0018
Revises: 20260223_0017
Create Date: 2026-02-23

Changes:
  - CheckConstraint ck_finance_positive_amount on finance_entries(amount > 0)
  - CheckConstraint ck_finance_type on finance_entries(type IN ('income','expense'))
  - CheckConstraint ck_task_category on tasks(category IN (...))
  - CheckConstraint ck_project_status on projects(status IN (...))
  - CheckConstraint ck_goal_status on goals(status IN (...))
  - CheckConstraint ck_goal_progress on goals(progress BETWEEN 0 AND 100)
  - Index ix_tasks_external_source on tasks(external_source)
  - ai_call_logs.organization_id → NOT NULL DEFAULT 1
"""

from alembic import op
import sqlalchemy as sa

revision = "20260223_0018"
down_revision = "20260223_0017"
branch_labels = None
depends_on = None


def _has_index(inspector: sa.Inspector, table: str, index_name: str) -> bool:
    return any(idx["name"] == index_name for idx in inspector.get_indexes(table))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    dialect = bind.dialect.name

    # ── Check constraints (SQLite ignores ALTER TABLE ADD CONSTRAINT,
    #    but they are enforced via CREATE TABLE in model metadata) ──
    if dialect != "sqlite":
        if "finance_entries" in tables:
            op.create_check_constraint(
                "ck_finance_positive_amount", "finance_entries", "amount > 0"
            )
            op.create_check_constraint(
                "ck_finance_type", "finance_entries",
                "type IN ('income', 'expense')"
            )

        if "tasks" in tables:
            op.create_check_constraint(
                "ck_task_category", "tasks",
                "category IN ('personal', 'business', 'health', 'finance', 'other')"
            )

        if "projects" in tables:
            op.create_check_constraint(
                "ck_project_status", "projects",
                "status IN ('active', 'completed', 'paused', 'archived')"
            )

        if "goals" in tables:
            op.create_check_constraint(
                "ck_goal_status", "goals",
                "status IN ('active', 'completed', 'paused', 'abandoned')"
            )
            op.create_check_constraint(
                "ck_goal_progress", "goals",
                "progress >= 0 AND progress <= 100"
            )

    # ── Index on tasks.external_source ──
    if "tasks" in tables and not _has_index(inspector, "tasks", "ix_tasks_external_source"):
        op.create_index(
            "ix_tasks_external_source", "tasks", ["external_source"], unique=False
        )

    # ── ai_call_logs.organization_id → NOT NULL with default 1 ──
    if "ai_call_logs" in tables and dialect != "sqlite":
        op.execute("UPDATE ai_call_logs SET organization_id = 1 WHERE organization_id IS NULL")
        op.alter_column(
            "ai_call_logs",
            "organization_id",
            existing_type=sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    dialect = bind.dialect.name

    # ── Revert ai_call_logs ──
    if "ai_call_logs" in tables and dialect != "sqlite":
        op.alter_column(
            "ai_call_logs",
            "organization_id",
            existing_type=sa.Integer(),
            nullable=True,
            server_default=None,
        )

    # ── Drop index ──
    if "tasks" in tables and _has_index(inspector, "tasks", "ix_tasks_external_source"):
        op.drop_index("ix_tasks_external_source", table_name="tasks")

    # ── Drop check constraints ──
    if dialect != "sqlite":
        if "goals" in tables:
            op.drop_constraint("ck_goal_progress", "goals", type_="check")
            op.drop_constraint("ck_goal_status", "goals", type_="check")
        if "projects" in tables:
            op.drop_constraint("ck_project_status", "projects", type_="check")
        if "tasks" in tables:
            op.drop_constraint("ck_task_category", "tasks", type_="check")
        if "finance_entries" in tables:
            op.drop_constraint("ck_finance_type", "finance_entries", type_="check")
            op.drop_constraint("ck_finance_positive_amount", "finance_entries", type_="check")
