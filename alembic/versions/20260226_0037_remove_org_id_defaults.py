"""Remove default=1 from organization_id in 8 tables

These ORM-level defaults silently assigned new rows to org 1 if the
application forgot to supply an explicit organization_id.  Removing
the server_default (where present) enforces that every INSERT must
provide the value explicitly.

Revision ID: 20260226_0037
Revises: 20260226_0036
Create Date: 2026-02-26 18:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "20260226_0037"
down_revision = "20260226_0036"
branch_labels = None
depends_on = None

# Tables that had default=1 on organization_id at the ORM layer.
# Some may also carry a server_default in the DB schema; we drop that too.
_TABLES = [
    "commands",
    "contacts",
    "finance_entries",
    "goals",
    "notes",
    "projects",
    "users",
    "profile_memory",
    "team_members",
    "daily_context",
    "avatar_memory",
]


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect == "sqlite":
        # SQLite doesn't support ALTER COLUMN; the ORM-level change is enough.
        return
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    for table in _TABLES:
        if table not in tables:
            continue
        cols = {c["name"] for c in inspector.get_columns(table)}
        if "organization_id" not in cols:
            continue
        op.alter_column(table, "organization_id", server_default=None)


def downgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        return
    for table in _TABLES:
        try:
            op.alter_column(
                table, "organization_id", server_default=sa.text("1")
            )
        except Exception:
            pass
