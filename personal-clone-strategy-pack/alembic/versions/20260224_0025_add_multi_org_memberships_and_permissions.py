"""Add multi-org memberships and org role permissions.

Revision ID: 20260224_0025
Revises: 20260224_0024
Create Date: 2026-02-24 17:45:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260224_0025"
down_revision: str | None = "0024"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "organization_memberships",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "user_id", name="uq_org_memberships_org_user"),
    )
    op.create_index(
        "ix_organization_memberships_organization_id",
        "organization_memberships",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_organization_memberships_user_id",
        "organization_memberships",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "organization_role_permissions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("permission", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "role", "permission", name="uq_org_role_permission"),
    )
    op.create_index(
        "ix_organization_role_permissions_organization_id",
        "organization_role_permissions",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_organization_role_permissions_permission",
        "organization_role_permissions",
        ["permission"],
        unique=False,
    )
    op.create_index(
        "ix_organization_role_permissions_role",
        "organization_role_permissions",
        ["role"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_organization_role_permissions_role", table_name="organization_role_permissions")
    op.drop_index("ix_organization_role_permissions_permission", table_name="organization_role_permissions")
    op.drop_index("ix_organization_role_permissions_organization_id", table_name="organization_role_permissions")
    op.drop_table("organization_role_permissions")

    op.drop_index("ix_organization_memberships_user_id", table_name="organization_memberships")
    op.drop_index("ix_organization_memberships_organization_id", table_name="organization_memberships")
    op.drop_table("organization_memberships")
