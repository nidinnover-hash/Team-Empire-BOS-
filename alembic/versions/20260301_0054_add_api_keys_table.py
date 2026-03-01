"""Add api_keys table.

Revision ID: 20260301_0054
Revises: 20260301_0053
"""

import sqlalchemy as sa
from alembic import op

revision = "20260301_0054"
down_revision = "20260301_0053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "organization_id",
            sa.Integer,
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("key_prefix", sa.String(12), nullable=False),
        sa.Column("key_hash", sa.String(128), nullable=False),
        sa.Column("scopes", sa.Text, nullable=False, server_default="*"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_api_keys_org_id", "api_keys", ["organization_id"])
    op.create_index("ix_api_keys_user_id", "api_keys", ["user_id"])
    op.create_index("ix_api_keys_key_prefix", "api_keys", ["key_prefix"])
    op.create_index("ix_api_keys_key_hash", "api_keys", ["key_hash"], unique=True)


def downgrade() -> None:
    op.drop_table("api_keys")
