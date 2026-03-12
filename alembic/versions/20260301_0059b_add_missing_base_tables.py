"""Add missing base tables omitted from earlier migrations.

Tables: approval_patterns, coaching_reports, invite_tokens, whatsapp_messages,
        media_attachments, system_health_logs, governance_policies,
        governance_violations.

Revision ID: 20260301_0059b
Revises: 20260301_0059
Create Date: 2026-03-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260301_0059b"
down_revision: str | None = "20260301_0059"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "approval_patterns" not in tables:
        op.create_table(
            "approval_patterns",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("organization_id", sa.Integer(), nullable=False),
            sa.Column("approval_type", sa.String(length=100), nullable=False),
            sa.Column("sample_payload", sa.JSON(), nullable=True),
            sa.Column("approved_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("rejected_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_auto_approve_enabled", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("auto_approve_threshold", sa.Float(), nullable=False, server_default="0.9"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_approval_patterns_organization_id", "approval_patterns", ["organization_id"])
        op.create_index("ix_approval_patterns_approval_type", "approval_patterns", ["approval_type"])

    if "coaching_reports" not in tables:
        op.create_table(
            "coaching_reports",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("organization_id", sa.Integer(), nullable=False),
            sa.Column("employee_id", sa.Integer(), nullable=True),
            sa.Column("department_id", sa.Integer(), nullable=True),
            sa.Column("report_type", sa.String(length=40), nullable=False, server_default="employee"),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("summary", sa.Text(), nullable=False, server_default=""),
            sa.Column("recommendations_json", sa.JSON(), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
            sa.Column("approved_by", sa.Integer(), nullable=True),
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["approved_by"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["department_id"], ["departments.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_coaching_reports_organization_id", "coaching_reports", ["organization_id"])
        op.create_index("ix_coaching_reports_employee_id", "coaching_reports", ["employee_id"])
        op.create_index("ix_coaching_reports_department_id", "coaching_reports", ["department_id"])
        op.create_index("ix_coaching_reports_report_type", "coaching_reports", ["report_type"])
        op.create_index("ix_coaching_reports_status", "coaching_reports", ["status"])

    if "invite_tokens" not in tables:
        op.create_table(
            "invite_tokens",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("organization_id", sa.Integer(), nullable=False),
            sa.Column("email", sa.String(length=320), nullable=False),
            sa.Column("token", sa.String(length=200), nullable=False),
            sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("token", name="uq_invite_tokens_token"),
        )
        op.create_index("ix_invite_tokens_organization_id", "invite_tokens", ["organization_id"])
        op.create_index("ix_invite_tokens_email", "invite_tokens", ["email"])
        op.create_index("ix_invite_tokens_token", "invite_tokens", ["token"])

    if "whatsapp_messages" not in tables:
        op.create_table(
            "whatsapp_messages",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("organization_id", sa.Integer(), nullable=False),
            sa.Column("integration_id", sa.Integer(), nullable=True),
            sa.Column("wa_message_id", sa.String(length=255), nullable=True),
            sa.Column("wa_contact_id", sa.String(length=100), nullable=True),
            sa.Column("direction", sa.String(length=20), nullable=False),
            sa.Column("from_number", sa.String(length=64), nullable=True),
            sa.Column("to_number", sa.String(length=64), nullable=True),
            sa.Column("message_type", sa.String(length=50), nullable=True),
            sa.Column("body_text", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=50), nullable=True),
            sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("raw_payload", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["integration_id"], ["integrations.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("organization_id", "wa_message_id", name="uq_wa_messages_org_message_id"),
        )
        op.create_index("ix_whatsapp_messages_organization_id", "whatsapp_messages", ["organization_id"])
        op.create_index("ix_whatsapp_messages_integration_id", "whatsapp_messages", ["integration_id"])
        op.create_index("ix_whatsapp_messages_wa_message_id", "whatsapp_messages", ["wa_message_id"])
        op.create_index("ix_whatsapp_messages_wa_contact_id", "whatsapp_messages", ["wa_contact_id"])
        op.create_index("ix_whatsapp_messages_direction", "whatsapp_messages", ["direction"])
        op.create_index("ix_whatsapp_messages_from_number", "whatsapp_messages", ["from_number"])
        op.create_index("ix_whatsapp_messages_to_number", "whatsapp_messages", ["to_number"])
        op.create_index("ix_whatsapp_messages_status", "whatsapp_messages", ["status"])
        op.create_index("ix_whatsapp_messages_occurred_at", "whatsapp_messages", ["occurred_at"])

    if "media_attachments" not in tables:
        op.create_table(
            "media_attachments",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("organization_id", sa.Integer(), nullable=False),
            sa.Column("uploaded_by", sa.Integer(), nullable=True),
            sa.Column("file_name", sa.String(length=500), nullable=False),
            sa.Column("original_name", sa.String(length=500), nullable=False),
            sa.Column("mime_type", sa.String(length=100), nullable=False),
            sa.Column("file_size_bytes", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("storage_backend", sa.String(length=20), nullable=False, server_default="local"),
            sa.Column("storage_path", sa.String(length=1000), nullable=False),
            sa.Column("entity_type", sa.String(length=50), nullable=True),
            sa.Column("entity_id", sa.Integer(), nullable=True),
            sa.Column("ai_tags_json", sa.JSON(), nullable=True),
            sa.Column("ai_summary", sa.Text(), nullable=True),
            sa.Column("is_processed", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_media_attachments_organization_id", "media_attachments", ["organization_id"])
        op.create_index("ix_media_attachments_entity_type", "media_attachments", ["entity_type"])
        op.create_index("ix_media_attachments_entity_id", "media_attachments", ["entity_id"])

    if "system_health_logs" not in tables:
        op.create_table(
            "system_health_logs",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("organization_id", sa.Integer(), nullable=True),
            sa.Column("category", sa.String(length=40), nullable=False),
            sa.Column("severity", sa.String(length=20), nullable=False, server_default="warning"),
            sa.Column("source", sa.String(length=100), nullable=False),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("details", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_system_health_logs_organization_id", "system_health_logs", ["organization_id"])
        op.create_index("ix_system_health_logs_category", "system_health_logs", ["category"])
        op.create_index("ix_system_health_logs_created_at", "system_health_logs", ["created_at"])

    if "governance_policies" not in tables:
        op.create_table(
            "governance_policies",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("organization_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("policy_type", sa.String(length=50), nullable=False, server_default="general"),
            sa.Column("rules_json", sa.JSON(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
            sa.Column("requires_ceo_approval", sa.Boolean(), nullable=False, server_default="true"),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_governance_policies_organization_id", "governance_policies", ["organization_id"])
        op.create_index("ix_governance_policies_policy_type", "governance_policies", ["policy_type"])
        op.create_index("ix_governance_policies_is_active", "governance_policies", ["is_active"])

    if "governance_violations" not in tables:
        op.create_table(
            "governance_violations",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("organization_id", sa.Integer(), nullable=False),
            sa.Column("policy_id", sa.Integer(), nullable=False),
            sa.Column("employee_id", sa.Integer(), nullable=True),
            sa.Column("violation_type", sa.String(length=100), nullable=False),
            sa.Column("details_json", sa.JSON(), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="open"),
            sa.Column("resolved_by", sa.Integer(), nullable=True),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["policy_id"], ["governance_policies.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["resolved_by"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_governance_violations_organization_id", "governance_violations", ["organization_id"])
        op.create_index("ix_governance_violations_policy_id", "governance_violations", ["policy_id"])
        op.create_index("ix_governance_violations_employee_id", "governance_violations", ["employee_id"])
        op.create_index("ix_governance_violations_status", "governance_violations", ["status"])


def downgrade() -> None:
    op.drop_table("governance_violations")
    op.drop_table("governance_policies")
    op.drop_table("system_health_logs")
    op.drop_table("media_attachments")
    op.drop_table("whatsapp_messages")
    op.drop_table("invite_tokens")
    op.drop_table("coaching_reports")
    op.drop_table("approval_patterns")
