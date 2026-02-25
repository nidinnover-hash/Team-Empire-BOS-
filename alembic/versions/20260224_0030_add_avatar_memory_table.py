"""add avatar memory table

Revision ID: 20260224_0030
Revises: 20260224_0029
Create Date: 2026-02-24 23:55:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260224_0030"
down_revision = "20260224_0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "avatar_memory",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("avatar_mode", sa.String(length=20), nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "avatar_mode", "key", name="uq_avatar_memory_org_mode_key"),
    )
    op.create_index("ix_avatar_memory_organization_id", "avatar_memory", ["organization_id"], unique=False)
    op.create_index("ix_avatar_memory_avatar_mode", "avatar_memory", ["avatar_mode"], unique=False)
    op.create_index("ix_avatar_memory_created_at", "avatar_memory", ["created_at"], unique=False)
    op.create_index("ix_avatar_memory_updated_at", "avatar_memory", ["updated_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_avatar_memory_updated_at", table_name="avatar_memory")
    op.drop_index("ix_avatar_memory_created_at", table_name="avatar_memory")
    op.drop_index("ix_avatar_memory_avatar_mode", table_name="avatar_memory")
    op.drop_index("ix_avatar_memory_organization_id", table_name="avatar_memory")
    op.drop_table("avatar_memory")
