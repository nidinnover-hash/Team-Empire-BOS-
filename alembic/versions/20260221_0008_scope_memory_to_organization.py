"""scope memory tables to organization

Revision ID: 20260221_0008
Revises: 20260221_0007
Create Date: 2026-02-21
"""

from alembic import op
import sqlalchemy as sa


revision = "20260221_0008"
down_revision = "20260221_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("profile_memory", schema=None) as batch_op:
        batch_op.add_column(sa.Column("organization_id", sa.Integer(), nullable=True, server_default="1"))
        batch_op.create_index("ix_profile_memory_organization_id", ["organization_id"], unique=False)

    with op.batch_alter_table("team_members", schema=None) as batch_op:
        batch_op.add_column(sa.Column("organization_id", sa.Integer(), nullable=True, server_default="1"))
        batch_op.create_index("ix_team_members_organization_id", ["organization_id"], unique=False)

    with op.batch_alter_table("daily_context", schema=None) as batch_op:
        batch_op.add_column(sa.Column("organization_id", sa.Integer(), nullable=True, server_default="1"))
        batch_op.create_index("ix_daily_context_organization_id", ["organization_id"], unique=False)

    op.execute("UPDATE profile_memory SET organization_id = 1 WHERE organization_id IS NULL")
    op.execute("UPDATE team_members SET organization_id = 1 WHERE organization_id IS NULL")
    op.execute("UPDATE daily_context SET organization_id = 1 WHERE organization_id IS NULL")

    with op.batch_alter_table("profile_memory", schema=None) as batch_op:
        batch_op.create_foreign_key(
            "fk_profile_memory_organization_id",
            "organizations",
            ["organization_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.alter_column("organization_id", nullable=False, server_default=None)
        batch_op.drop_constraint("uq_profile_memory_key", type_="unique")
        batch_op.create_unique_constraint(
            "uq_profile_memory_org_key",
            ["organization_id", "key"],
        )

    with op.batch_alter_table("team_members", schema=None) as batch_op:
        batch_op.create_foreign_key(
            "fk_team_members_organization_id",
            "organizations",
            ["organization_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.alter_column("organization_id", nullable=False, server_default=None)

    with op.batch_alter_table("daily_context", schema=None) as batch_op:
        batch_op.create_foreign_key(
            "fk_daily_context_organization_id",
            "organizations",
            ["organization_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.alter_column("organization_id", nullable=False, server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("profile_memory", schema=None) as batch_op:
        batch_op.drop_constraint("uq_profile_memory_org_key", type_="unique")
        batch_op.create_unique_constraint("uq_profile_memory_key", ["key"])
        batch_op.drop_constraint("fk_profile_memory_organization_id", type_="foreignkey")
        batch_op.drop_index("ix_profile_memory_organization_id")
        batch_op.drop_column("organization_id")

    with op.batch_alter_table("team_members", schema=None) as batch_op:
        batch_op.drop_constraint("fk_team_members_organization_id", type_="foreignkey")
        batch_op.drop_index("ix_team_members_organization_id")
        batch_op.drop_column("organization_id")

    with op.batch_alter_table("daily_context", schema=None) as batch_op:
        batch_op.drop_constraint("fk_daily_context_organization_id", type_="foreignkey")
        batch_op.drop_index("ix_daily_context_organization_id")
        batch_op.drop_column("organization_id")
