"""Add money_approval_matrices table.

Revision ID: 20260312_0092
Revises: 20260312_0091
Create Date: 2026-03-12
"""
from alembic import op
import sqlalchemy as sa

revision = "20260312_0092"
down_revision = "20260312_0091"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "money_approval_matrices",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("action_type", sa.String(50), nullable=False),
        sa.Column("amount_min", sa.Float(), nullable=False, server_default="0"),
        sa.Column("amount_max", sa.Float(), nullable=False, server_default="999999999"),
        sa.Column("allowed_roles", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_money_approval_matrices_organization_id", "money_approval_matrices", ["organization_id"])
    op.create_index("ix_money_approval_matrices_action_type", "money_approval_matrices", ["action_type"])


def downgrade() -> None:
    op.drop_index("ix_money_approval_matrices_action_type", table_name="money_approval_matrices")
    op.drop_index("ix_money_approval_matrices_organization_id", table_name="money_approval_matrices")
    op.drop_table("money_approval_matrices")
