"""Add webhook_endpoints and webhook_deliveries tables.

Revision ID: 20260301_0053
Revises: 20260228_0052
Create Date: 2026-03-01
"""

import sqlalchemy as sa
from alembic import op

revision = "20260301_0053"
down_revision = "20260228_0052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "webhook_endpoints",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "organization_id",
            sa.Integer,
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("secret_encrypted", sa.Text, nullable=False),
        sa.Column("event_types", sa.JSON, nullable=False, server_default="[]"),
        sa.Column(
            "is_active", sa.Boolean, nullable=False, server_default=sa.text("1")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("organization_id", "url", name="uq_webhook_org_url"),
    )
    op.create_index(
        "ix_webhook_endpoints_org_id", "webhook_endpoints", ["organization_id"]
    )
    op.create_index(
        "ix_webhook_endpoints_is_active", "webhook_endpoints", ["is_active"]
    )

    op.create_table(
        "webhook_deliveries",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "webhook_endpoint_id",
            sa.Integer,
            sa.ForeignKey("webhook_endpoints.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "organization_id",
            sa.Integer,
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("event", sa.String(100), nullable=False),
        sa.Column("payload_json", sa.JSON, nullable=False, server_default="{}"),
        sa.Column(
            "status", sa.String(30), nullable=False, server_default="'pending'"
        ),
        sa.Column("response_status_code", sa.Integer, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column(
            "attempt_count", sa.Integer, nullable=False, server_default=sa.text("1")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_webhook_deliveries_endpoint_id",
        "webhook_deliveries",
        ["webhook_endpoint_id"],
    )
    op.create_index(
        "ix_webhook_deliveries_org_id", "webhook_deliveries", ["organization_id"]
    )
    op.create_index(
        "ix_webhook_deliveries_event", "webhook_deliveries", ["event"]
    )
    op.create_index(
        "ix_webhook_deliveries_status", "webhook_deliveries", ["status"]
    )
    op.create_index(
        "ix_webhook_deliveries_created_at", "webhook_deliveries", ["created_at"]
    )


def downgrade() -> None:
    op.drop_table("webhook_deliveries")
    op.drop_table("webhook_endpoints")
