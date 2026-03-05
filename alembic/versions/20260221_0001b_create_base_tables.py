"""Create base tables that were never explicitly migrated.

Only creates tables that don't already exist and aren't created by other migrations.
Uses the ORM models as the source of truth.

Revision ID: 20260221_0001b
Revises: 20260221_0001
Create Date: 2026-02-21
"""
import sqlalchemy as sa
from alembic import op

revision = "20260221_0001b"
down_revision = "20260221_0001"
branch_labels = None
depends_on = None

# Tables that have their own create_table in other migrations — skip these
SKIP_TABLES = {
    "users", "approvals", "events",  # 0001
    "organizations",  # 0002
    "executions",  # 0003
    "integrations",  # 0004
    "profile_memory", "daily_context", "team_members",  # 0005
    "emails",  # 0006
    "daily_task_plans",  # 0007
    "daily_runs",  # 0009
    "decision_traces",  # 0014
    "employees", "integration_signals", "metric_snapshots",
    "decision_logs", "policy_rules", "weekly_reports",  # 0019
    "ceo_control_configs", "compliance_snapshots",  # 0020
    "github_repo_snapshots", "github_audit_events",
    "ceo_monitoring_configs",  # 0021
    "chat_messages",  # 0022
    "scheduler_job_runs",  # 0024
    "org_memberships", "org_permissions",  # 0025
    "clone_performance_weekly",  # 0026
    "clone_control_configs", "clone_control_snapshots",
    "clone_strategy_entries",  # 0027
    "social_posts",  # 0029
    "avatar_memory",  # 0030
    "self_learning_runs",  # 0036
    "notifications",  # 0039
    "autonomy_policy_configs", "autonomy_policy_versions",  # 0050
    "webhooks", "webhook_event_logs",  # 0053
    "api_keys",  # 0054
    "workforce_teams", "workforce_analytics_snapshots",  # 0057
    "trend_counters",  # 0058
    "location_records",  # 0063
    "contact_pipeline_histories",  # 0066
    "workspaces",  # 0070
    "share_packets",  # 0072
    "decision_cards",  # 0073
    "memory_embeddings",  # 0074
    # alembic's own table
    "alembic_version",
}


def upgrade() -> None:
    from app.db.base import Base
    from app.models.registry import load_all_models

    load_all_models()

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    # Only create tables that are NOT already handled by other migrations
    tables_to_create = []
    for table in Base.metadata.sorted_tables:
        if table.name in SKIP_TABLES:
            continue
        if table.name in existing_tables:
            continue
        tables_to_create.append(table)

    if tables_to_create:
        Base.metadata.create_all(bind=bind, tables=tables_to_create, checkfirst=True)


def downgrade() -> None:
    pass
