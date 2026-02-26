"""Add notifications table.

Revision ID: 20260226_0039
Revises: 20260226_0038
Create Date: 2026-02-26
"""
from alembic import op
import sqlalchemy as sa

revision = "20260226_0039"
down_revision = "20260226_0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "organization_id",
            sa.Integer,
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        ),
        sa.Column("type", sa.String(50), nullable=False, index=True),
        sa.Column("severity", sa.String(20), nullable=False, server_default="info"),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("source", sa.String(100), nullable=True),
        sa.Column("entity_type", sa.String(100), nullable=True),
        sa.Column("entity_id", sa.Integer, nullable=True),
        sa.Column("is_read", sa.Boolean, nullable=False, server_default=sa.text("false"), index=True),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, index=True),
    )


def downgrade() -> None:
    op.drop_table("notifications")
