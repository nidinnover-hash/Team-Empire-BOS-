"""Add webhook retry fields (next_retry_at, max_retries, max_retry_attempts).

Revision ID: 20260301_0055
Revises: 20260301_0054
"""

import sqlalchemy as sa
from alembic import op

revision = "20260301_0055"
down_revision = "20260301_0054"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "webhook_deliveries",
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "webhook_deliveries",
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="5"),
    )
    op.create_index(
        "ix_webhook_deliveries_next_retry_at",
        "webhook_deliveries",
        ["next_retry_at"],
    )
    op.add_column(
        "webhook_endpoints",
        sa.Column(
            "max_retry_attempts", sa.Integer(), nullable=False, server_default="5",
        ),
    )


def downgrade() -> None:
    op.drop_column("webhook_endpoints", "max_retry_attempts")
    op.drop_index(
        "ix_webhook_deliveries_next_retry_at",
        table_name="webhook_deliveries",
    )
    op.drop_column("webhook_deliveries", "max_retries")
    op.drop_column("webhook_deliveries", "next_retry_at")
