"""Drop unused organization_role_permissions table.

Revision ID: 20260226_0038
Revises: 20260226_0037
Create Date: 2026-02-26
"""
from alembic import op
import sqlalchemy as sa

revision = "20260226_0038"
down_revision = "20260226_0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("organization_role_permissions")


def downgrade() -> None:
    op.create_table(
        "organization_role_permissions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "organization_id",
            sa.Integer,
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("role", sa.String(50), nullable=False, index=True),
        sa.Column("permission", sa.String(100), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "organization_id", "role", "permission", name="uq_org_role_permission"
        ),
    )
