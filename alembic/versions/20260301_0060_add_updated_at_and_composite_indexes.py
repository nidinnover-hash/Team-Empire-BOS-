"""Add updated_at to mutable models and composite indexes for common queries.

Revision ID: 20260301_0060
Revises: 20260301_0059
Create Date: 2026-03-01
"""

from alembic import op
from sqlalchemy import Column, DateTime, text

revision = "20260301_0060"
down_revision = "20260301_0059b"
branch_labels = None
depends_on = None

# Tables that need updated_at (mutable models only)
_UPDATED_AT_TABLES = [
    "approval_patterns",
    "coaching_reports",
    "contacts",
    "daily_task_plans",
    "daily_runs",
    "emails",
    "goals",
    "invite_tokens",
    "notes",
    "notifications",
    "whatsapp_messages",
]

# Composite indexes for common query patterns
_INDEXES = [
    ("ix_tasks_org_is_done", "tasks", ["organization_id", "is_done"]),
    ("ix_notifications_org_is_read", "notifications", ["organization_id", "is_read"]),
    ("ix_conversations_org_status", "conversations", ["organization_id", "status"]),
    ("ix_daily_task_plans_org_date_status", "daily_task_plans", ["organization_id", "date", "status"]),
    ("ix_chat_messages_user_id", "chat_messages", ["user_id"]),
    ("ix_executions_triggered_by", "executions", ["triggered_by"]),
]


def _has_index(conn, index_name: str) -> bool:
    dialect = conn.dialect.name
    if dialect == "sqlite":
        rows = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='index' AND name=:n"),
            {"n": index_name},
        ).fetchall()
        return len(rows) > 0
    rows = conn.execute(
        text("SELECT 1 FROM pg_indexes WHERE indexname = :n"),
        {"n": index_name},
    ).fetchall()
    return len(rows) > 0


def _has_column(conn, table: str, column: str) -> bool:
    dialect = conn.dialect.name
    if dialect == "sqlite":
        rows = conn.execute(text(f"PRAGMA table_info('{table}')")).fetchall()
        return any(row[1] == column for row in rows)
    rows = conn.execute(
        text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = :t AND column_name = :c"
        ),
        {"t": table, "c": column},
    ).fetchall()
    return len(rows) > 0


def _table_exists(conn, table: str) -> bool:
    dialect = conn.dialect.name
    if dialect == "sqlite":
        rows = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name=:t"),
            {"t": table},
        ).fetchall()
        return len(rows) > 0
    rows = conn.execute(
        text("SELECT 1 FROM information_schema.tables WHERE table_name = :t AND table_schema = 'public'"),
        {"t": table},
    ).fetchall()
    return len(rows) > 0


def upgrade() -> None:
    conn = op.get_bind()

    # Add updated_at columns
    for table in _UPDATED_AT_TABLES:
        if not _table_exists(conn, table):
            continue
        if not _has_column(conn, table, "updated_at"):
            op.add_column(
                table,
                Column("updated_at", DateTime(timezone=True), nullable=True),
            )
            # Backfill: set updated_at = created_at for existing rows
            if _has_column(conn, table, "created_at"):
                op.execute(text(f"UPDATE {table} SET updated_at = created_at WHERE updated_at IS NULL"))

    # Add composite indexes
    for idx_name, table, columns in _INDEXES:
        if not _table_exists(conn, table):
            continue
        if not _has_index(conn, idx_name):
            op.create_index(idx_name, table, columns)


def downgrade() -> None:
    # Drop indexes
    for idx_name, table, _columns in reversed(_INDEXES):
        op.drop_index(idx_name, table_name=table)

    # Drop updated_at columns
    for table in reversed(_UPDATED_AT_TABLES):
        op.drop_column(table, "updated_at")
