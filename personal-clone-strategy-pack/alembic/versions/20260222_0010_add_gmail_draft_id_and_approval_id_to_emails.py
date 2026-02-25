"""add gmail_draft_id and approval_id to emails

Revision ID: 20260222_0010
Revises: 20260221_0009
Create Date: 2026-02-22
"""

from alembic import op
import sqlalchemy as sa


revision = "20260222_0010"
down_revision = "20260221_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # gmail_draft_id: stores the Gmail API draft ID so we can track the draft
    # in Gmail and use it for idempotent send.
    op.add_column(
        "emails",
        sa.Column("gmail_draft_id", sa.String(length=200), nullable=True),
    )
    op.create_index("ix_emails_gmail_draft_id", "emails", ["gmail_draft_id"], unique=False)

    # approval_id: DB-level link from email to its send_message approval.
    # Replaces the Python-side loop that searched all approved approvals.
    op.add_column(
        "emails",
        sa.Column("approval_id", sa.Integer(), nullable=True),
    )
    op.create_index("ix_emails_approval_id", "emails", ["approval_id"], unique=False)

    # Foreign key only on non-SQLite (SQLite used in tests doesn't support it well)
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.create_foreign_key(
            "fk_emails_approval_id_approvals",
            "emails",
            "approvals",
            ["approval_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.drop_constraint("fk_emails_approval_id_approvals", "emails", type_="foreignkey")
    op.drop_index("ix_emails_approval_id", table_name="emails")
    op.drop_column("emails", "approval_id")
    op.drop_index("ix_emails_gmail_draft_id", table_name="emails")
    op.drop_column("emails", "gmail_draft_id")
