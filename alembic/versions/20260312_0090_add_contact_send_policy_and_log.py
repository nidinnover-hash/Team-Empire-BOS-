"""Add contact_send_policies and contact_send_logs (can_send enforcement).

Revision ID: 20260312_0090
Revises: 20260312_0089
Create Date: 2026-03-12
"""
from alembic import op
import sqlalchemy as sa

revision = "20260312_0090"
down_revision = "20260312_0089"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "contact_send_policies",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("channel", sa.String(50), nullable=False),
        sa.Column("max_per_contact_per_day", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_contact_send_policies_organization_id", "contact_send_policies", ["organization_id"])
    op.create_index("ix_contact_send_policies_channel", "contact_send_policies", ["channel"])

    op.create_table(
        "contact_send_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("contact_id", sa.String(255), nullable=False),
        sa.Column("channel", sa.String(50), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_contact_send_logs_organization_id", "contact_send_logs", ["organization_id"])
    op.create_index("ix_contact_send_logs_contact_id", "contact_send_logs", ["contact_id"])
    op.create_index("ix_contact_send_logs_sent_at", "contact_send_logs", ["sent_at"])
    op.create_index(
        "ix_contact_send_logs_org_contact_channel_sent",
        "contact_send_logs",
        ["organization_id", "contact_id", "channel", "sent_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_contact_send_logs_org_contact_channel_sent", table_name="contact_send_logs")
    op.drop_index("ix_contact_send_logs_sent_at", table_name="contact_send_logs")
    op.drop_index("ix_contact_send_logs_contact_id", table_name="contact_send_logs")
    op.drop_index("ix_contact_send_logs_organization_id", table_name="contact_send_logs")
    op.drop_table("contact_send_logs")
    op.drop_index("ix_contact_send_policies_channel", table_name="contact_send_policies")
    op.drop_index("ix_contact_send_policies_organization_id", table_name="contact_send_policies")
    op.drop_table("contact_send_policies")
