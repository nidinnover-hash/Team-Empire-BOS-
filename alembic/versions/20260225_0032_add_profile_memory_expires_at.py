"""add expires_at to profile_memory

Revision ID: 20260225_0032
Revises: 20260224_0031
Create Date: 2026-02-25 14:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260225_0032"
down_revision = "20260224_0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("profile_memory")}
    if "expires_at" not in columns:
        op.add_column(
            "profile_memory",
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("profile_memory")}
    if "expires_at" in columns:
        op.drop_column("profile_memory", "expires_at")
