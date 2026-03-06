"""add workflow definitions and workflow runs

Revision ID: 20260307_0083
Revises: 20260306_0082
"""

import sqlalchemy as sa
from alembic import op


revision = "20260307_0083"
down_revision = "20260306_0082"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workflow_definitions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("workspace_id", sa.Integer(), sa.ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("trigger_mode", sa.String(length=20), nullable=False, server_default="manual"),
        sa.Column("trigger_spec_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("steps_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("defaults_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("risk_level", sa.String(length=20), nullable=False, server_default="medium"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("organization_id", "slug", name="uq_workflow_definition_org_slug"),
    )
    op.create_index("ix_workflow_definitions_org_status_created_at", "workflow_definitions", ["organization_id", "status", "created_at"])
    op.create_index("ix_workflow_definitions_slug", "workflow_definitions", ["slug"])
    op.create_index("ix_workflow_definitions_organization_id", "workflow_definitions", ["organization_id"])
    op.create_index("ix_workflow_definitions_workspace_id", "workflow_definitions", ["workspace_id"])

    op.create_table(
        "workflow_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("workspace_id", sa.Integer(), sa.ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True),
        sa.Column("workflow_definition_id", sa.Integer(), sa.ForeignKey("workflow_definitions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workflow_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("trigger_source", sa.String(length=20), nullable=False, server_default="manual"),
        sa.Column("trigger_signal_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("current_step_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("requested_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("started_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approval_id", sa.Integer(), sa.ForeignKey("approvals.id", ondelete="SET NULL"), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("plan_snapshot_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("input_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("context_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("result_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("organization_id", "idempotency_key", name="uq_workflow_run_org_idempotency_key"),
    )
    op.create_index("ix_workflow_runs_org_status_created_at", "workflow_runs", ["organization_id", "status", "created_at"])
    op.create_index("ix_workflow_runs_org_definition_created_at", "workflow_runs", ["organization_id", "workflow_definition_id", "created_at"])
    op.create_index("ix_workflow_runs_organization_id", "workflow_runs", ["organization_id"])
    op.create_index("ix_workflow_runs_workspace_id", "workflow_runs", ["workspace_id"])
    op.create_index("ix_workflow_runs_workflow_definition_id", "workflow_runs", ["workflow_definition_id"])
    op.create_index("ix_workflow_runs_trigger_signal_id", "workflow_runs", ["trigger_signal_id"])

    op.create_table(
        "workflow_step_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("workflow_run_id", sa.Integer(), sa.ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step_index", sa.Integer(), nullable=False),
        sa.Column("step_key", sa.String(length=120), nullable=False),
        sa.Column("action_type", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("approval_id", sa.Integer(), sa.ForeignKey("approvals.id", ondelete="SET NULL"), nullable=True),
        sa.Column("execution_id", sa.Integer(), sa.ForeignKey("executions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("input_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("output_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("organization_id", "workflow_run_id", "step_index", name="uq_workflow_step_run_org_run_step"),
    )
    op.create_index("ix_workflow_step_runs_org_status_created_at", "workflow_step_runs", ["organization_id", "status", "created_at"])
    op.create_index("ix_workflow_step_runs_organization_id", "workflow_step_runs", ["organization_id"])
    op.create_index("ix_workflow_step_runs_workflow_run_id", "workflow_step_runs", ["workflow_run_id"])
    op.create_index("ix_workflow_step_runs_approval_id", "workflow_step_runs", ["approval_id"])
    op.create_index("ix_workflow_step_runs_execution_id", "workflow_step_runs", ["execution_id"])


def downgrade() -> None:
    op.drop_index("ix_workflow_step_runs_execution_id", table_name="workflow_step_runs")
    op.drop_index("ix_workflow_step_runs_approval_id", table_name="workflow_step_runs")
    op.drop_index("ix_workflow_step_runs_workflow_run_id", table_name="workflow_step_runs")
    op.drop_index("ix_workflow_step_runs_organization_id", table_name="workflow_step_runs")
    op.drop_index("ix_workflow_step_runs_org_status_created_at", table_name="workflow_step_runs")
    op.drop_table("workflow_step_runs")
    op.drop_index("ix_workflow_runs_trigger_signal_id", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_workflow_definition_id", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_workspace_id", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_organization_id", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_org_definition_created_at", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_org_status_created_at", table_name="workflow_runs")
    op.drop_table("workflow_runs")
    op.drop_index("ix_workflow_definitions_workspace_id", table_name="workflow_definitions")
    op.drop_index("ix_workflow_definitions_organization_id", table_name="workflow_definitions")
    op.drop_index("ix_workflow_definitions_slug", table_name="workflow_definitions")
    op.drop_index("ix_workflow_definitions_org_status_created_at", table_name="workflow_definitions")
    op.drop_table("workflow_definitions")
