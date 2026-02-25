"""add last_sync_status to integrations

Revision ID: 20260225_0033
Revises: 20260225_0032
Create Date: 2026-02-25 14:45:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260225_0033"
down_revision = "20260225_0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("integrations")}
    if "last_sync_status" not in columns:
        op.add_column(
            "integrations",
            sa.Column("last_sync_status", sa.String(length=30), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("integrations")}
    if "last_sync_status" in columns:
        op.drop_column("integrations", "last_sync_status")

