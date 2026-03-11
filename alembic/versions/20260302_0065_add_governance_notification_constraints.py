"""Add CHECK constraints and composite indexes for governance, notification, and user tables.

Revision ID: 20260302_0065
Revises: 20260302_0064
Create Date: 2026-03-02
"""
import sqlalchemy as sa
from alembic import op

revision = "20260302_0065"
down_revision = "20260302_0064"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # -- CHECK constraints --------------------------------------------------
    try:
        op.create_check_constraint(
            "ck_governance_policy_type",
            "governance_policies",
            "policy_type IN ('general', 'performance', 'compliance', 'security', 'operational')",
        )
    except Exception:
        pass
    try:
        op.create_check_constraint(
            "ck_governance_violation_status",
            "governance_violations",
            "status IN ('open', 'resolved', 'dismissed')",
        )
    except Exception:
        pass
    try:
        op.create_check_constraint(
            "ck_notification_severity",
            "notifications",
            "severity IN ('info', 'warning', 'error', 'critical')",
        )
    except Exception:
        pass
    try:
        op.create_check_constraint(
            "ck_user_role",
            "users",
            "role IN ('STAFF', 'ADMIN', 'CEO', 'MANAGER', 'EMPLOYEE', 'PERSONAL_CEO')",
        )
    except Exception:
        pass

    # -- Composite indexes for common query patterns -----------------------
    existing_gp = {i["name"] for i in inspector.get_indexes("governance_policies")}
    if "ix_governance_policies_org_active" not in existing_gp:
        op.create_index(
            "ix_governance_policies_org_active",
            "governance_policies",
            ["organization_id", "is_active"],
        )

    existing_gv = {i["name"] for i in inspector.get_indexes("governance_violations")}
    if "ix_governance_violations_org_status" not in existing_gv:
        op.create_index(
            "ix_governance_violations_org_status",
            "governance_violations",
            ["organization_id", "status"],
        )

    existing_notif = {i["name"] for i in inspector.get_indexes("notifications")}
    if "ix_notifications_org_user_unread" not in existing_notif:
        op.create_index(
            "ix_notifications_org_user_unread",
            "notifications",
            ["organization_id", "user_id", "is_read", "created_at"],
        )


def downgrade() -> None:
    op.drop_index("ix_notifications_org_user_unread", table_name="notifications")
    op.drop_index("ix_governance_violations_org_status", table_name="governance_violations")
    op.drop_index("ix_governance_policies_org_active", table_name="governance_policies")
    op.drop_constraint("ck_user_role", "users", type_="check")
    op.drop_constraint("ck_notification_severity", "notifications", type_="check")
    op.drop_constraint("ck_governance_violation_status", "governance_violations", type_="check")
    op.drop_constraint("ck_governance_policy_type", "governance_policies", type_="check")
