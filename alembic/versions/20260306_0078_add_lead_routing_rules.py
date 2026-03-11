"""add lead routing rules table

Revision ID: 20260306_0078
Revises: 20260306_0077
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260306_0078"
down_revision: str | None = "20260306_0077"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "lead_routing_rules" not in tables:
        op.create_table(
            "lead_routing_rules",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("owner_company_id", sa.Integer(), nullable=False),
            sa.Column("lead_type", sa.String(length=50), nullable=False),
            sa.Column("target_company_id", sa.Integer(), nullable=False),
            sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
            sa.Column("routing_reason", sa.String(length=500), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_by_user_id", sa.Integer(), nullable=True),
            sa.Column("updated_by_user_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["owner_company_id"], ["organizations.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["target_company_id"], ["organizations.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "owner_company_id",
                "lead_type",
                "priority",
                name="uq_lead_routing_rule_owner_type_priority",
            ),
        )
        op.create_index(op.f("ix_lead_routing_rules_owner_company_id"), "lead_routing_rules", ["owner_company_id"], unique=False)
        op.create_index(op.f("ix_lead_routing_rules_lead_type"), "lead_routing_rules", ["lead_type"], unique=False)
        op.create_index(op.f("ix_lead_routing_rules_target_company_id"), "lead_routing_rules", ["target_company_id"], unique=False)
        op.create_index(op.f("ix_lead_routing_rules_priority"), "lead_routing_rules", ["priority"], unique=False)
        op.create_index(op.f("ix_lead_routing_rules_is_active"), "lead_routing_rules", ["is_active"], unique=False)
        try:
            op.create_check_constraint(
                "ck_lead_routing_rule_priority",
                "lead_routing_rules",
                "priority >= 1 AND priority <= 1000",
            )
        except Exception:
            pass
        try:
            op.create_check_constraint(
                "ck_lead_routing_rule_lead_type",
                "lead_routing_rules",
                "lead_type IN ('general', 'study_abroad', 'recruitment')",
            )
        except Exception:
            pass
        op.alter_column("lead_routing_rules", "priority", server_default=None)
        op.alter_column("lead_routing_rules", "is_active", server_default=None)


def downgrade() -> None:
    op.drop_constraint("ck_lead_routing_rule_lead_type", "lead_routing_rules", type_="check")
    op.drop_constraint("ck_lead_routing_rule_priority", "lead_routing_rules", type_="check")
    op.drop_index(op.f("ix_lead_routing_rules_is_active"), table_name="lead_routing_rules")
    op.drop_index(op.f("ix_lead_routing_rules_priority"), table_name="lead_routing_rules")
    op.drop_index(op.f("ix_lead_routing_rules_target_company_id"), table_name="lead_routing_rules")
    op.drop_index(op.f("ix_lead_routing_rules_lead_type"), table_name="lead_routing_rules")
    op.drop_index(op.f("ix_lead_routing_rules_owner_company_id"), table_name="lead_routing_rules")
    op.drop_table("lead_routing_rules")
