"""Add recruitment_routing_rules table.

Revision ID: 20260312_0093
Revises: 20260312_0092
Create Date: 2026-03-12
"""
from alembic import op
import sqlalchemy as sa

revision = "20260312_0093"
down_revision = "20260312_0092"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recruitment_routing_rules",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("region", sa.String(100), nullable=True),
        sa.Column("product_line", sa.String(100), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("assign_to_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["assign_to_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_recruitment_routing_rules_organization_id", "recruitment_routing_rules", ["organization_id"])
    op.create_index("ix_recruitment_routing_rules_region", "recruitment_routing_rules", ["region"])
    op.create_index("ix_recruitment_routing_rules_product_line", "recruitment_routing_rules", ["product_line"])


def downgrade() -> None:
    op.drop_index("ix_recruitment_routing_rules_product_line", table_name="recruitment_routing_rules")
    op.drop_index("ix_recruitment_routing_rules_region", table_name="recruitment_routing_rules")
    op.drop_index("ix_recruitment_routing_rules_organization_id", table_name="recruitment_routing_rules")
    op.drop_table("recruitment_routing_rules")
