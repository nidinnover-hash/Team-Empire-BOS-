"""add emails table

Revision ID: 20260221_0006
Revises: 20260221_0005
Create Date: 2026-02-21
"""

from alembic import op
import sqlalchemy as sa


revision = "20260221_0006"
down_revision = "20260221_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "emails",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("gmail_id", sa.String(length=200), nullable=False),
        sa.Column("thread_id", sa.String(length=200), nullable=True),
        sa.Column("from_address", sa.String(length=300), nullable=True),
        sa.Column("to_address", sa.String(length=300), nullable=True),
        sa.Column("subject", sa.String(length=500), nullable=True),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("category", sa.String(length=50), nullable=True),  # team/lead/vendor/other
        sa.Column("ai_summary", sa.Text(), nullable=True),
        sa.Column("draft_reply", sa.Text(), nullable=True),
        sa.Column("reply_approved", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("reply_sent", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("gmail_id", name="uq_emails_gmail_id"),
    )
    op.create_index("ix_emails_organization_id", "emails", ["organization_id"], unique=False)
    op.create_index("ix_emails_thread_id", "emails", ["thread_id"], unique=False)
    op.create_index("ix_emails_received_at", "emails", ["received_at"], unique=False)
    op.create_index("ix_emails_is_read", "emails", ["is_read"], unique=False)
    op.create_index("ix_emails_category", "emails", ["category"], unique=False)
    op.create_index("ix_emails_reply_sent", "emails", ["reply_sent"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_emails_reply_sent", table_name="emails")
    op.drop_index("ix_emails_category", table_name="emails")
    op.drop_index("ix_emails_is_read", table_name="emails")
    op.drop_index("ix_emails_received_at", table_name="emails")
    op.drop_index("ix_emails_thread_id", table_name="emails")
    op.drop_index("ix_emails_organization_id", table_name="emails")
    op.drop_table("emails")
