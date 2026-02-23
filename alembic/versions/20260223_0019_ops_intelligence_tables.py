"""Create ops-intelligence tables: employees, integration_signals, metrics, decision_logs, policy_rules, weekly_reports

Revision ID: 0019
Revises: 0018
Create Date: 2026-02-23
"""

from alembic import op
import sqlalchemy as sa

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- employees --
    op.create_table(
        "employees",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("role", sa.String(100), nullable=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("github_username", sa.String(100), nullable=True),
        sa.Column("clickup_user_id", sa.String(100), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("organization_id", "email", name="uq_employee_org_email"),
    )

    # -- integration_signals --
    op.create_table(
        "integration_signals",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True),
        sa.Column("source", sa.String(50), nullable=False, index=True),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("employee_id", sa.Integer, sa.ForeignKey("employees.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_json", sa.Text, nullable=False, server_default="{}"),
        sa.Column("hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("organization_id", "source", "external_id", name="uq_signal_org_source_ext"),
    )

    # -- task_metrics_weekly --
    op.create_table(
        "task_metrics_weekly",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True),
        sa.Column("employee_id", sa.Integer, sa.ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False, index=True),
        sa.Column("week_start_date", sa.Date, nullable=False),
        sa.Column("tasks_assigned", sa.Integer, nullable=False, server_default="0"),
        sa.Column("tasks_completed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("on_time_rate", sa.Float, nullable=False, server_default="0"),
        sa.Column("avg_cycle_time_hours", sa.Float, nullable=False, server_default="0"),
        sa.Column("reopen_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("organization_id", "employee_id", "week_start_date", name="uq_task_metric_week"),
    )

    # -- code_metrics_weekly --
    op.create_table(
        "code_metrics_weekly",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True),
        sa.Column("employee_id", sa.Integer, sa.ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False, index=True),
        sa.Column("week_start_date", sa.Date, nullable=False),
        sa.Column("commits", sa.Integer, nullable=False, server_default="0"),
        sa.Column("prs_opened", sa.Integer, nullable=False, server_default="0"),
        sa.Column("prs_merged", sa.Integer, nullable=False, server_default="0"),
        sa.Column("reviews_done", sa.Integer, nullable=False, server_default="0"),
        sa.Column("issue_links", sa.Integer, nullable=False, server_default="0"),
        sa.Column("files_touched_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("organization_id", "employee_id", "week_start_date", name="uq_code_metric_week"),
    )

    # -- comms_metrics_weekly --
    op.create_table(
        "comms_metrics_weekly",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True),
        sa.Column("employee_id", sa.Integer, sa.ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False, index=True),
        sa.Column("week_start_date", sa.Date, nullable=False),
        sa.Column("emails_sent", sa.Integer, nullable=False, server_default="0"),
        sa.Column("emails_replied", sa.Integer, nullable=False, server_default="0"),
        sa.Column("median_reply_time_minutes", sa.Float, nullable=False, server_default="0"),
        sa.Column("escalation_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("organization_id", "employee_id", "week_start_date", name="uq_comms_metric_week"),
    )

    # -- decision_logs --
    op.create_table(
        "decision_logs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True),
        sa.Column("decision_type", sa.String(20), nullable=False),
        sa.Column("context", sa.Text, nullable=False),
        sa.Column("objective", sa.Text, nullable=False),
        sa.Column("constraints", sa.Text, nullable=True),
        sa.Column("deadline", sa.String(100), nullable=True),
        sa.Column("success_metric", sa.Text, nullable=True),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("risk", sa.Text, nullable=True),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # -- policy_rules --
    op.create_table(
        "policy_rules",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("rule_text", sa.Text, nullable=False),
        sa.Column("examples_json", sa.Text, nullable=False, server_default="[]"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # -- weekly_reports --
    op.create_table(
        "weekly_reports",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True),
        sa.Column("week_start_date", sa.Date, nullable=False),
        sa.Column("report_type", sa.String(50), nullable=False),
        sa.Column("content_markdown", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("weekly_reports")
    op.drop_table("policy_rules")
    op.drop_table("decision_logs")
    op.drop_table("comms_metrics_weekly")
    op.drop_table("code_metrics_weekly")
    op.drop_table("task_metrics_weekly")
    op.drop_table("integration_signals")
    op.drop_table("employees")
