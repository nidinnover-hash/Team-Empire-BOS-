"""Add CRM pipeline fields to contacts table.

Revision ID: 20260302_0066
Revises: 20260302_0065
Create Date: 2026-03-02
"""
import sqlalchemy as sa
from alembic import op

revision = "20260302_0066"
down_revision = "20260302_0065"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("contacts", sa.Column("pipeline_stage", sa.String(30), nullable=False, server_default="new"))
    op.add_column("contacts", sa.Column("lead_score", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("contacts", sa.Column("lead_source", sa.String(50), nullable=True))
    op.add_column("contacts", sa.Column("deal_value", sa.Float(), nullable=True))
    op.add_column("contacts", sa.Column("expected_close_date", sa.DateTime(timezone=True), nullable=True))
    op.add_column("contacts", sa.Column("last_contacted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("contacts", sa.Column("next_follow_up_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("contacts", sa.Column("tags", sa.String(500), nullable=True))

    op.create_index("ix_contacts_pipeline_stage", "contacts", ["pipeline_stage"])
    op.create_index("ix_contacts_next_follow_up_at", "contacts", ["next_follow_up_at"])

    op.create_check_constraint(
        "ck_contact_pipeline_stage",
        "contacts",
        "pipeline_stage IN ('new', 'contacted', 'qualified', 'proposal', 'negotiation', 'won', 'lost')",
    )
    op.create_check_constraint(
        "ck_contact_lead_score",
        "contacts",
        "lead_score >= 0 AND lead_score <= 100",
    )


def downgrade() -> None:
    op.drop_constraint("ck_contact_lead_score", "contacts", type_="check")
    op.drop_constraint("ck_contact_pipeline_stage", "contacts", type_="check")
    op.drop_index("ix_contacts_next_follow_up_at", "contacts")
    op.drop_index("ix_contacts_pipeline_stage", "contacts")
    op.drop_column("contacts", "tags")
    op.drop_column("contacts", "next_follow_up_at")
    op.drop_column("contacts", "last_contacted_at")
    op.drop_column("contacts", "expected_close_date")
    op.drop_column("contacts", "deal_value")
    op.drop_column("contacts", "lead_source")
    op.drop_column("contacts", "lead_score")
    op.drop_column("contacts", "pipeline_stage")
