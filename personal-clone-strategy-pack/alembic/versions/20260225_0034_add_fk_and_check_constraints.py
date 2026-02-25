"""add FK and CHECK constraints for model hardening

Revision ID: 20260225_0034
Revises: 20260225_0033
Create Date: 2026-02-25 20:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260225_0034"
down_revision = "20260225_0033"
branch_labels = None
depends_on = None


def _has_constraint(inspector, table: str, constraint_name: str) -> bool:
    """Check if a named constraint already exists (CHECK or FK)."""
    for ck in inspector.get_check_constraints(table):
        if ck.get("name") == constraint_name:
            return True
    for fk in inspector.get_foreign_keys(table):
        if fk.get("name") == constraint_name:
            return True
    return False


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    # -- Approval.status CHECK -----------------------------------------------
    if "approvals" in tables and not _has_constraint(inspector, "approvals", "ck_approval_status"):
        op.create_check_constraint(
            "ck_approval_status",
            "approvals",
            "status IN ('pending', 'approved', 'rejected')",
        )

    # -- Approval.requested_by FK -------------------------------------------
    if "approvals" in tables and dialect != "sqlite":
        if not _has_constraint(inspector, "approvals", "fk_approval_requested_by_user"):
            op.create_foreign_key(
                "fk_approval_requested_by_user",
                "approvals",
                "users",
                ["requested_by"],
                ["id"],
                ondelete="RESTRICT",
            )

    # -- DailyTaskPlan.status CHECK ------------------------------------------
    if "daily_task_plans" in tables and not _has_constraint(inspector, "daily_task_plans", "ck_daily_task_plan_status"):
        op.create_check_constraint(
            "ck_daily_task_plan_status",
            "daily_task_plans",
            "status IN ('draft', 'approved', 'sent')",
        )

    # -- Task.is_done CHECK (fix boolean for PostgreSQL) ---------------------
    if "tasks" in tables and dialect != "sqlite":
        try:
            op.drop_constraint("ck_task_done_has_completed_at", "tasks", type_="check")
        except Exception:
            pass  # constraint may not exist yet
        op.create_check_constraint(
            "ck_task_done_has_completed_at",
            "tasks",
            "NOT is_done OR completed_at IS NOT NULL",
        )

    # -- DailyRun.requested_by FK -------------------------------------------
    if "daily_runs" in tables and dialect != "sqlite":
        if not _has_constraint(inspector, "daily_runs", "fk_daily_run_requested_by_user"):
            op.create_foreign_key(
                "fk_daily_run_requested_by_user",
                "daily_runs",
                "users",
                ["requested_by"],
                ["id"],
                ondelete="RESTRICT",
            )

    # -- DecisionTrace.actor_user_id FK -------------------------------------
    if "decision_traces" in tables and dialect != "sqlite":
        if not _has_constraint(inspector, "decision_traces", "fk_decision_trace_actor_user"):
            op.create_foreign_key(
                "fk_decision_trace_actor_user",
                "decision_traces",
                "users",
                ["actor_user_id"],
                ["id"],
                ondelete="SET NULL",
            )

    # -- DecisionTrace.daily_run_id FK --------------------------------------
    if "decision_traces" in tables and "daily_runs" in tables and dialect != "sqlite":
        if not _has_constraint(inspector, "decision_traces", "fk_decision_trace_daily_run"):
            op.create_foreign_key(
                "fk_decision_trace_daily_run",
                "decision_traces",
                "daily_runs",
                ["daily_run_id"],
                ["id"],
                ondelete="SET NULL",
            )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect != "sqlite":
        try:
            op.drop_constraint("fk_decision_trace_daily_run", "decision_traces", type_="foreignkey")
        except Exception:
            pass
        try:
            op.drop_constraint("fk_decision_trace_actor_user", "decision_traces", type_="foreignkey")
        except Exception:
            pass
        try:
            op.drop_constraint("fk_daily_run_requested_by_user", "daily_runs", type_="foreignkey")
        except Exception:
            pass
        try:
            op.drop_constraint("fk_approval_requested_by_user", "approvals", type_="foreignkey")
        except Exception:
            pass
        # Restore old CHECK for tasks
        try:
            op.drop_constraint("ck_task_done_has_completed_at", "tasks", type_="check")
        except Exception:
            pass
        op.create_check_constraint(
            "ck_task_done_has_completed_at",
            "tasks",
            "is_done = 0 OR completed_at IS NOT NULL",
        )

    try:
        op.drop_constraint("ck_daily_task_plan_status", "daily_task_plans", type_="check")
    except Exception:
        pass
    try:
        op.drop_constraint("ck_approval_status", "approvals", type_="check")
    except Exception:
        pass
