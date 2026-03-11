"""Add CHECK constraints for status and category columns.

Revision ID: 20260302_0061
Revises: 20260301_0060
Create Date: 2026-03-02
"""

import sqlalchemy as sa
from alembic import op

revision = "20260302_0061"
down_revision = "20260301_0060"
branch_labels = None
depends_on = None

# (table, constraint_name, column, allowed_values)
_CONSTRAINTS: list[tuple[str, str, str, list[str]]] = [
    (
        "employees",
        "ck_employee_employment_status",
        "employment_status",
        ["active", "offboarded"],
    ),
    (
        "integrations",
        "ck_integration_status",
        "status",
        ["connected", "disconnected"],
    ),
    (
        "integrations",
        "ck_integration_last_sync_status",
        "last_sync_status",
        ["ok", "error", "unknown"],
    ),
    (
        "coaching_reports",
        "ck_coaching_report_status",
        "status",
        ["pending", "approved", "rejected"],
    ),
    (
        "coaching_reports",
        "ck_coaching_report_type",
        "report_type",
        ["employee", "department", "org"],
    ),
    (
        "clone_memory_entries",
        "ck_clone_memory_outcome",
        "outcome",
        ["success", "partial", "failure"],
    ),
    (
        "clone_memory_entries",
        "ck_clone_memory_category",
        "category",
        ["sales", "support", "operations", "onboarding", "negotiation", "general"],
    ),
    (
        "media_attachments",
        "ck_media_storage_backend",
        "storage_backend",
        ["local", "s3"],
    ),
    (
        "system_health_logs",
        "ck_system_health_category",
        "category",
        ["api_error", "sync_failure", "ai_fallback", "slow_query", "scheduler_error"],
    ),
    (
        "system_health_logs",
        "ck_system_health_severity",
        "severity",
        ["info", "warning", "error", "critical"],
    ),
]


def _table_exists(conn, table: str) -> bool:
    rows = conn.execute(
        sa.text("SELECT 1 FROM information_schema.tables WHERE table_name = :t AND table_schema = 'public'"),
        {"t": table},
    ).fetchall()
    return len(rows) > 0


def _constraint_exists(conn, name: str) -> bool:
    rows = conn.execute(
        sa.text("SELECT 1 FROM pg_constraint WHERE conname = :n"),
        {"n": name},
    ).fetchall()
    return len(rows) > 0


def upgrade() -> None:
    conn = op.get_bind()
    for table, name, column, values in _CONSTRAINTS:
        if not _table_exists(conn, table):
            continue
        if _constraint_exists(conn, name):
            continue
        vals = ", ".join(f"'{v}'" for v in values)
        # nullable columns need IS NULL allowance
        nullable = column in ("last_sync_status",)
        expr = f"{column} IN ({vals})"
        if nullable:
            expr = f"({expr} OR {column} IS NULL)"
        op.create_check_constraint(name, table, expr)


def downgrade() -> None:
    for table, name, _column, _values in reversed(_CONSTRAINTS):
        op.drop_constraint(name, table, type_="check")
