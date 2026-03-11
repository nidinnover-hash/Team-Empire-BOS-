"""Add TOTP MFA fields to users table.

Revision ID: 20260226_0042
Revises: 20260226_0041
Create Date: 2026-02-26
"""
import sqlalchemy as sa
from alembic import op

revision = "20260226_0042"
down_revision = "20260226_0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {c["name"] for c in inspector.get_columns("users")}

    if "totp_secret" not in existing:
        op.add_column(
            "users",
            sa.Column("totp_secret", sa.String(64), nullable=True),
        )
    if "mfa_enabled" not in existing:
        op.add_column(
            "users",
            sa.Column("mfa_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        )


def downgrade() -> None:
    op.drop_column("users", "mfa_enabled")
    op.drop_column("users", "totp_secret")
