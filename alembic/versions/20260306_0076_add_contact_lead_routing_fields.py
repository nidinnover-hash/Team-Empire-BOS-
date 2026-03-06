"""add lead routing fields to contacts

Revision ID: 20260306_0076
Revises: 20260305_0075
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260306_0076"
down_revision: str | None = "20260305_0075"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "contacts",
        sa.Column("lead_owner_company_id", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "contacts",
        sa.Column("routed_company_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "contacts",
        sa.Column("lead_type", sa.String(length=50), nullable=False, server_default="general"),
    )
    op.add_column(
        "contacts",
        sa.Column("routing_status", sa.String(length=30), nullable=False, server_default="unrouted"),
    )
    op.add_column(
        "contacts",
        sa.Column("routing_reason", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "contacts",
        sa.Column("routed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "contacts",
        sa.Column("routed_by_user_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "contacts",
        sa.Column("source_channel", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "contacts",
        sa.Column("campaign_name", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "contacts",
        sa.Column("partner_id", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "contacts",
        sa.Column("qualified_score", sa.Integer(), nullable=True),
    )
    op.add_column(
        "contacts",
        sa.Column("qualified_status", sa.String(length=30), nullable=False, server_default="unqualified"),
    )
    op.add_column(
        "contacts",
        sa.Column("qualification_notes", sa.Text(), nullable=True),
    )

    op.create_foreign_key(
        "fk_contacts_lead_owner_company_id_org",
        "contacts",
        "organizations",
        ["lead_owner_company_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_contacts_routed_company_id_org",
        "contacts",
        "organizations",
        ["routed_company_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_contacts_routed_by_user_id_user",
        "contacts",
        "users",
        ["routed_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_index(op.f("ix_contacts_lead_owner_company_id"), "contacts", ["lead_owner_company_id"], unique=False)
    op.create_index(op.f("ix_contacts_routed_company_id"), "contacts", ["routed_company_id"], unique=False)
    op.create_index(op.f("ix_contacts_lead_type"), "contacts", ["lead_type"], unique=False)
    op.create_index(op.f("ix_contacts_routing_status"), "contacts", ["routing_status"], unique=False)
    op.create_index(op.f("ix_contacts_source_channel"), "contacts", ["source_channel"], unique=False)
    op.create_index(op.f("ix_contacts_campaign_name"), "contacts", ["campaign_name"], unique=False)
    op.create_index(op.f("ix_contacts_partner_id"), "contacts", ["partner_id"], unique=False)
    op.create_index(op.f("ix_contacts_qualified_status"), "contacts", ["qualified_status"], unique=False)

    op.create_check_constraint(
        "ck_contact_lead_type",
        "contacts",
        "lead_type IN ('general', 'study_abroad', 'recruitment')",
    )
    op.create_check_constraint(
        "ck_contact_routing_status",
        "contacts",
        "routing_status IN ('unrouted', 'under_review', 'routed', 'accepted', 'rejected', 'closed')",
    )
    op.create_check_constraint(
        "ck_contact_qualified_status",
        "contacts",
        "qualified_status IN ('unqualified', 'qualified', 'disqualified', 'needs_review')",
    )
    op.create_check_constraint(
        "ck_contact_qualified_score",
        "contacts",
        "qualified_score IS NULL OR (qualified_score >= 0 AND qualified_score <= 100)",
    )

    op.alter_column("contacts", "lead_owner_company_id", server_default=None)
    op.alter_column("contacts", "lead_type", server_default=None)
    op.alter_column("contacts", "routing_status", server_default=None)
    op.alter_column("contacts", "qualified_status", server_default=None)


def downgrade() -> None:
    op.drop_constraint("ck_contact_qualified_score", "contacts", type_="check")
    op.drop_constraint("ck_contact_qualified_status", "contacts", type_="check")
    op.drop_constraint("ck_contact_routing_status", "contacts", type_="check")
    op.drop_constraint("ck_contact_lead_type", "contacts", type_="check")
    op.drop_index(op.f("ix_contacts_qualified_status"), table_name="contacts")
    op.drop_index(op.f("ix_contacts_partner_id"), table_name="contacts")
    op.drop_index(op.f("ix_contacts_campaign_name"), table_name="contacts")
    op.drop_index(op.f("ix_contacts_source_channel"), table_name="contacts")
    op.drop_index(op.f("ix_contacts_routing_status"), table_name="contacts")
    op.drop_index(op.f("ix_contacts_lead_type"), table_name="contacts")
    op.drop_index(op.f("ix_contacts_routed_company_id"), table_name="contacts")
    op.drop_index(op.f("ix_contacts_lead_owner_company_id"), table_name="contacts")
    op.drop_constraint("fk_contacts_routed_by_user_id_user", "contacts", type_="foreignkey")
    op.drop_constraint("fk_contacts_routed_company_id_org", "contacts", type_="foreignkey")
    op.drop_constraint("fk_contacts_lead_owner_company_id_org", "contacts", type_="foreignkey")
    op.drop_column("contacts", "qualification_notes")
    op.drop_column("contacts", "qualified_status")
    op.drop_column("contacts", "qualified_score")
    op.drop_column("contacts", "partner_id")
    op.drop_column("contacts", "campaign_name")
    op.drop_column("contacts", "source_channel")
    op.drop_column("contacts", "routed_by_user_id")
    op.drop_column("contacts", "routed_at")
    op.drop_column("contacts", "routing_reason")
    op.drop_column("contacts", "routing_status")
    op.drop_column("contacts", "lead_type")
    op.drop_column("contacts", "routed_company_id")
    op.drop_column("contacts", "lead_owner_company_id")
