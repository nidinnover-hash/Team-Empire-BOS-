"""Add performance composite indexes.

Revision ID: 0023
Revises: 0022
Create Date: 2026-02-24
"""

from alembic import op
from sqlalchemy import text

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def _has_index(conn, index_name: str) -> bool:
    """Check whether an index already exists (SQLite + PostgreSQL safe)."""
    dialect = conn.dialect.name
    if dialect == "sqlite":
        rows = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='index' AND name=:n"),
            {"n": index_name},
        ).fetchall()
        return len(rows) > 0
    # PostgreSQL / others
    rows = conn.execute(
        text("SELECT 1 FROM pg_indexes WHERE indexname = :n"),
        {"n": index_name},
    ).fetchall()
    return len(rows) > 0


def upgrade() -> None:
    conn = op.get_bind()

    # chat_messages: dashboard cleanup queries filter by org + order by created_at
    idx1 = "ix_chat_messages_org_created"
    if not _has_index(conn, idx1):
        op.create_index(idx1, "chat_messages", ["organization_id", "created_at"])

    # emails: dashboard query filters by org + is_read, orders by received_at
    idx2 = "ix_emails_org_read_received"
    if not _has_index(conn, idx2):
        op.create_index(idx2, "emails", ["organization_id", "is_read", "received_at"])


def downgrade() -> None:
    op.drop_index("ix_emails_org_read_received", table_name="emails")
    op.drop_index("ix_chat_messages_org_created", table_name="chat_messages")
