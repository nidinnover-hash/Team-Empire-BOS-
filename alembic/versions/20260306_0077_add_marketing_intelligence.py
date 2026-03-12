"""add marketing intelligence table

Revision ID: 20260306_0077
Revises: 20260306_0076
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260306_0077"
down_revision: str | None = "20260306_0076"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "marketing_intelligence" not in tables:
        op.create_table(
            "marketing_intelligence",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("owner_company_id", sa.Integer(), nullable=False),
            sa.Column("source_company_id", sa.Integer(), nullable=False),
            sa.Column("category", sa.String(length=80), nullable=False),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("summary", sa.Text(), nullable=False),
            sa.Column("confidence", sa.Float(), nullable=True),
            sa.Column("priority", sa.String(length=30), nullable=True),
            sa.Column("suggested_action", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=30), nullable=False, server_default="submitted"),
            sa.Column("created_by_user_id", sa.Integer(), nullable=True),
            sa.Column("reviewed_by_user_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["owner_company_id"], ["organizations.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["source_company_id"], ["organizations.id"], ondelete="RESTRICT"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_marketing_intelligence_owner_company_id"), "marketing_intelligence", ["owner_company_id"], unique=False)
        op.create_index(op.f("ix_marketing_intelligence_source_company_id"), "marketing_intelligence", ["source_company_id"], unique=False)
        op.create_index(op.f("ix_marketing_intelligence_category"), "marketing_intelligence", ["category"], unique=False)
        op.create_index(op.f("ix_marketing_intelligence_priority"), "marketing_intelligence", ["priority"], unique=False)
        op.create_index(op.f("ix_marketing_intelligence_status"), "marketing_intelligence", ["status"], unique=False)
        op.create_index(op.f("ix_marketing_intelligence_created_at"), "marketing_intelligence", ["created_at"], unique=False)
        op.create_check_constraint(
            "ck_marketing_intelligence_status",
            "marketing_intelligence",
            "status IN ('submitted', 'reviewing', 'accepted', 'rejected', 'applied')",
        )
        op.create_check_constraint(
            "ck_marketing_intelligence_priority",
            "marketing_intelligence",
            "priority IS NULL OR priority IN ('low', 'medium', 'high', 'critical')",
        )
        op.create_check_constraint(
            "ck_marketing_intelligence_confidence",
            "marketing_intelligence",
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
        )
        op.alter_column("marketing_intelligence", "status", server_default=None)


def downgrade() -> None:
    op.drop_constraint("ck_marketing_intelligence_confidence", "marketing_intelligence", type_="check")
    op.drop_constraint("ck_marketing_intelligence_priority", "marketing_intelligence", type_="check")
    op.drop_constraint("ck_marketing_intelligence_status", "marketing_intelligence", type_="check")
    op.drop_index(op.f("ix_marketing_intelligence_created_at"), table_name="marketing_intelligence")
    op.drop_index(op.f("ix_marketing_intelligence_status"), table_name="marketing_intelligence")
    op.drop_index(op.f("ix_marketing_intelligence_priority"), table_name="marketing_intelligence")
    op.drop_index(op.f("ix_marketing_intelligence_category"), table_name="marketing_intelligence")
    op.drop_index(op.f("ix_marketing_intelligence_source_company_id"), table_name="marketing_intelligence")
    op.drop_index(op.f("ix_marketing_intelligence_owner_company_id"), table_name="marketing_intelligence")
    op.drop_table("marketing_intelligence")
