"""Add lead_type and sla_hours to recruitment_routing_rules.

Revision ID: 20260312_0095
Revises: 20260312_0094
Create Date: 2026-03-12

"""
from alembic import op
import sqlalchemy as sa

revision = "20260312_0095"
down_revision = "20260312_0094"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "recruitment_routing_rules",
        sa.Column("lead_type", sa.String(50), nullable=True),
    )
    op.add_column(
        "recruitment_routing_rules",
        sa.Column("sla_hours", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_recruitment_routing_rules_lead_type",
        "recruitment_routing_rules",
        ["lead_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_recruitment_routing_rules_lead_type", table_name="recruitment_routing_rules")
    op.drop_column("recruitment_routing_rules", "sla_hours")
    op.drop_column("recruitment_routing_rules", "lead_type")
