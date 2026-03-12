"""Add missing indexes for common query patterns.

Revision ID: 20260302_0062
Revises: 20260302_0061
Create Date: 2026-03-02
"""

import sqlalchemy as sa
from alembic import op

revision = "20260302_0062"
down_revision = "20260302_0061"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Contact.name — used in ORDER BY for list_contacts
    existing_con = {i["name"] for i in inspector.get_indexes("contacts")}
    if "ix_contacts_name" not in existing_con:
        op.create_index("ix_contacts_name", "contacts", ["name"])

    # Event entity lookups — polymorphic (entity_type, entity_id) pair
    existing_evt = {i["name"] for i in inspector.get_indexes("events")}
    if "ix_events_entity_type_entity_id" not in existing_evt:
        op.create_index(
            "ix_events_entity_type_entity_id",
            "events",
            ["entity_type", "entity_id"],
        )

    # Employee composite for list_by_department filtered queries
    existing_emp = {i["name"] for i in inspector.get_indexes("employees")}
    if "ix_employees_org_dept_active" not in existing_emp:
        op.create_index(
            "ix_employees_org_dept_active",
            "employees",
            ["organization_id", "department_id", "is_active"],
        )

    # MediaAttachment polymorphic entity lookup
    existing_ma = {i["name"] for i in inspector.get_indexes("media_attachments")}
    if "ix_media_attachments_entity" not in existing_ma:
        op.create_index(
            "ix_media_attachments_entity",
            "media_attachments",
            ["entity_type", "entity_id"],
        )

    # CoachingReport common filter (org + report_type + status)
    existing_cr = {i["name"] for i in inspector.get_indexes("coaching_reports")}
    if "ix_coaching_reports_org_type_status" not in existing_cr:
        op.create_index(
            "ix_coaching_reports_org_type_status",
            "coaching_reports",
            ["organization_id", "report_type", "status"],
        )


def downgrade() -> None:
    op.drop_index("ix_coaching_reports_org_type_status", table_name="coaching_reports")
    op.drop_index("ix_media_attachments_entity", table_name="media_attachments")
    op.drop_index("ix_employees_org_dept_active", table_name="employees")
    op.drop_index("ix_events_entity_type_entity_id", table_name="events")
    op.drop_index("ix_contacts_name", table_name="contacts")
