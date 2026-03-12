"""add batch 17-20 CRM tables

Revision ID: 20260310_0087
Revises: 20260310_0086
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260310_0087"
down_revision: str | None = "20260310_0086"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    # ── Batch 17 ─────────────────────────────────────────────────────────

    if "customer_health_scores" not in tables:
        op.create_table(
            "customer_health_scores",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("contact_id", sa.Integer, nullable=False, index=True),
            sa.Column("overall_score", sa.Integer, nullable=False, default=0),
            sa.Column("usage_score", sa.Integer, nullable=False, default=0),
            sa.Column("engagement_score", sa.Integer, nullable=False, default=0),
            sa.Column("support_score", sa.Integer, nullable=False, default=0),
            sa.Column("payment_score", sa.Integer, nullable=False, default=0),
            sa.Column("risk_level", sa.String(20), nullable=False, server_default="medium"),
            sa.Column("factors_json", sa.Text, nullable=True),
            sa.Column("previous_score", sa.Integer, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if "availability_slots" not in tables:
        op.create_table(
            "availability_slots",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("user_id", sa.Integer, nullable=False, index=True),
            sa.Column("day_of_week", sa.Integer, nullable=False),
            sa.Column("start_time", sa.String(10), nullable=False),
            sa.Column("end_time", sa.String(10), nullable=False),
            sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if "meeting_bookings" not in tables:
        op.create_table(
            "meeting_bookings",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("host_user_id", sa.Integer, nullable=False),
            sa.Column("contact_id", sa.Integer, nullable=True),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="confirmed"),
            sa.Column("location", sa.String(500), nullable=True),
            sa.Column("notes", sa.Text, nullable=True),
            sa.Column("reminder_sent", sa.Boolean, nullable=False, server_default=sa.text("false")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if "signature_requests" not in tables:
        op.create_table(
            "signature_requests",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("document_url", sa.String(500), nullable=False),
            sa.Column("deal_id", sa.Integer, nullable=True),
            sa.Column("contact_id", sa.Integer, nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
            sa.Column("signing_order", sa.Integer, nullable=False, server_default="1"),
            sa.Column("signers_json", sa.Text, nullable=True),
            sa.Column("expires_at", sa.Date, nullable=True),
            sa.Column("signed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("sent_by_user_id", sa.Integer, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if "leaderboard_entries" not in tables:
        op.create_table(
            "leaderboard_entries",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("user_id", sa.Integer, nullable=False),
            sa.Column("period", sa.String(20), nullable=False),
            sa.Column("period_type", sa.String(20), nullable=False, server_default="monthly"),
            sa.Column("total_revenue", sa.Numeric(14, 2), nullable=False, server_default="0"),
            sa.Column("deals_closed", sa.Integer, nullable=False, server_default="0"),
            sa.Column("deals_created", sa.Integer, nullable=False, server_default="0"),
            sa.Column("activities_count", sa.Integer, nullable=False, server_default="0"),
            sa.Column("rank", sa.Integer, nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if "dedup_rules" not in tables:
        op.create_table(
            "dedup_rules",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("match_fields", sa.Text, nullable=False),
            sa.Column("merge_strategy", sa.String(30), nullable=False, server_default="manual"),
            sa.Column("confidence_threshold", sa.Numeric(5, 2), nullable=False, server_default="0.80"),
            sa.Column("auto_merge", sa.Boolean, nullable=False, server_default=sa.text("false")),
            sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
            sa.Column("total_matches", sa.Integer, nullable=False, server_default="0"),
            sa.Column("total_merges", sa.Integer, nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if "stage_gates" not in tables:
        op.create_table(
            "stage_gates",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("stage", sa.String(50), nullable=False),
            sa.Column("requirement_type", sa.String(50), nullable=False),
            sa.Column("field_name", sa.String(100), nullable=True),
            sa.Column("description", sa.String(500), nullable=True),
            sa.Column("is_blocking", sa.Boolean, nullable=False, server_default=sa.text("true")),
            sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if "stage_gate_overrides" not in tables:
        op.create_table(
            "stage_gate_overrides",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("gate_id", sa.Integer, sa.ForeignKey("stage_gates.id", ondelete="CASCADE"), nullable=False),
            sa.Column("deal_id", sa.Integer, nullable=False),
            sa.Column("overridden_by_user_id", sa.Integer, nullable=False),
            sa.Column("reason", sa.Text, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if "activity_goals" not in tables:
        op.create_table(
            "activity_goals",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("user_id", sa.Integer, nullable=False),
            sa.Column("activity_type", sa.String(50), nullable=False),
            sa.Column("period", sa.String(20), nullable=False),
            sa.Column("period_type", sa.String(20), nullable=False, server_default="weekly"),
            sa.Column("target", sa.Integer, nullable=False, server_default="0"),
            sa.Column("current", sa.Integer, nullable=False, server_default="0"),
            sa.Column("streak", sa.Integer, nullable=False, server_default="0"),
            sa.Column("best_streak", sa.Integer, nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    # ── Batch 18 ─────────────────────────────────────────────────────────

    if "subscription_plans" not in tables:
        op.create_table(
            "subscription_plans",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("billing_cycle", sa.String(20), nullable=False, server_default="monthly"),
            sa.Column("price", sa.Numeric(14, 2), nullable=False, server_default="0"),
            sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
            sa.Column("features_json", sa.Text, nullable=True),
            sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if "subscriptions" not in tables:
        op.create_table(
            "subscriptions",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("plan_id", sa.Integer, sa.ForeignKey("subscription_plans.id", ondelete="CASCADE"), nullable=False),
            sa.Column("contact_id", sa.Integer, nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="active"),
            sa.Column("start_date", sa.Date, nullable=True),
            sa.Column("end_date", sa.Date, nullable=True),
            sa.Column("next_billing_date", sa.Date, nullable=True),
            sa.Column("mrr", sa.Numeric(14, 2), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if "drip_campaigns" not in tables:
        op.create_table(
            "drip_campaigns",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("description", sa.Text, nullable=True),
            sa.Column("trigger_event", sa.String(100), nullable=True),
            sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
            sa.Column("total_enrolled", sa.Integer, nullable=False, server_default="0"),
            sa.Column("total_completed", sa.Integer, nullable=False, server_default="0"),
            sa.Column("total_unsubscribed", sa.Integer, nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if "drip_steps" not in tables:
        op.create_table(
            "drip_steps",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("organization_id", sa.Integer, nullable=False, index=True),
            sa.Column("campaign_id", sa.Integer, sa.ForeignKey("drip_campaigns.id", ondelete="CASCADE"), nullable=False),
            sa.Column("step_order", sa.Integer, nullable=False, server_default="1"),
            sa.Column("delay_days", sa.Integer, nullable=False, server_default="1"),
            sa.Column("subject", sa.String(300), nullable=True),
            sa.Column("body", sa.Text, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if "drip_enrollments" not in tables:
        op.create_table(
            "drip_enrollments",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("organization_id", sa.Integer, nullable=False, index=True),
            sa.Column("campaign_id", sa.Integer, sa.ForeignKey("drip_campaigns.id", ondelete="CASCADE"), nullable=False),
            sa.Column("contact_id", sa.Integer, nullable=False),
            sa.Column("current_step", sa.Integer, nullable=False, server_default="0"),
            sa.Column("status", sa.String(20), nullable=False, server_default="active"),
            sa.Column("enrolled_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        )

    if "lead_score_rules" not in tables:
        op.create_table(
            "lead_score_rules",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("rule_type", sa.String(30), nullable=False, server_default="attribute"),
            sa.Column("field_name", sa.String(100), nullable=True),
            sa.Column("operator", sa.String(20), nullable=True),
            sa.Column("value", sa.String(200), nullable=True),
            sa.Column("score_delta", sa.Integer, nullable=False, server_default="0"),
            sa.Column("weight", sa.Numeric(5, 2), nullable=False, server_default="1.0"),
            sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
            sa.Column("conditions_json", sa.Text, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if "onboarding_templates" not in tables:
        op.create_table(
            "onboarding_templates",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("description", sa.Text, nullable=True),
            sa.Column("steps_json", sa.Text, nullable=True),
            sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if "onboarding_checklists" not in tables:
        op.create_table(
            "onboarding_checklists",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("template_id", sa.Integer, sa.ForeignKey("onboarding_templates.id", ondelete="CASCADE"), nullable=False),
            sa.Column("contact_id", sa.Integer, nullable=True),
            sa.Column("deal_id", sa.Integer, nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="in_progress"),
            sa.Column("progress_json", sa.Text, nullable=True),
            sa.Column("completed_steps", sa.Integer, nullable=False, server_default="0"),
            sa.Column("total_steps", sa.Integer, nullable=False, server_default="0"),
            sa.Column("assigned_user_id", sa.Integer, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        )

    if "forecast_scenarios" not in tables:
        op.create_table(
            "forecast_scenarios",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("period", sa.String(20), nullable=False),
            sa.Column("scenario_type", sa.String(30), nullable=False, server_default="base"),
            sa.Column("total_pipeline", sa.Numeric(14, 2), nullable=False, server_default="0"),
            sa.Column("weighted_value", sa.Numeric(14, 2), nullable=False, server_default="0"),
            sa.Column("expected_close", sa.Numeric(14, 2), nullable=False, server_default="0"),
            sa.Column("assumptions_json", sa.Text, nullable=True),
            sa.Column("notes", sa.Text, nullable=True),
            sa.Column("created_by_user_id", sa.Integer, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if "feature_requests" not in tables:
        op.create_table(
            "feature_requests",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("title", sa.String(300), nullable=False),
            sa.Column("description", sa.Text, nullable=True),
            sa.Column("category", sa.String(50), nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="open"),
            sa.Column("priority", sa.String(20), nullable=False, server_default="medium"),
            sa.Column("votes", sa.Integer, nullable=False, server_default="0"),
            sa.Column("submitted_by_user_id", sa.Integer, nullable=True),
            sa.Column("contact_id", sa.Integer, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if "audit_entries" not in tables:
        op.create_table(
            "audit_entries",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("entity_type", sa.String(50), nullable=False),
            sa.Column("entity_id", sa.Integer, nullable=False),
            sa.Column("action", sa.String(30), nullable=False),
            sa.Column("user_id", sa.Integer, nullable=True),
            sa.Column("changes_json", sa.Text, nullable=True),
            sa.Column("snapshot_json", sa.Text, nullable=True),
            sa.Column("ip_address", sa.String(45), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    # ── Batch 19 ─────────────────────────────────────────────────────────

    if "call_logs" not in tables:
        op.create_table(
            "call_logs",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("organization_id", sa.Integer, nullable=False, index=True),
            sa.Column("user_id", sa.Integer, nullable=False),
            sa.Column("contact_id", sa.Integer, nullable=True),
            sa.Column("deal_id", sa.Integer, nullable=True),
            sa.Column("direction", sa.String(20), nullable=False, server_default="outbound"),
            sa.Column("duration_seconds", sa.Integer, nullable=False, server_default="0"),
            sa.Column("outcome", sa.String(30), nullable=True),
            sa.Column("recording_url", sa.Text, nullable=True),
            sa.Column("notes", sa.Text, nullable=True),
            sa.Column("called_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if "drip_step_events" not in tables:
        op.create_table(
            "drip_step_events",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("organization_id", sa.Integer, nullable=False, index=True),
            sa.Column("campaign_id", sa.Integer, nullable=False),
            sa.Column("step_id", sa.Integer, nullable=False),
            sa.Column("enrollment_id", sa.Integer, nullable=False),
            sa.Column("contact_id", sa.Integer, nullable=False),
            sa.Column("event_type", sa.String(30), nullable=False),
            sa.Column("metadata_json", sa.String(2000), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if "deal_splits" not in tables:
        op.create_table(
            "deal_splits",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("organization_id", sa.Integer, nullable=False, index=True),
            sa.Column("deal_id", sa.Integer, nullable=False, index=True),
            sa.Column("user_id", sa.Integer, nullable=False),
            sa.Column("split_pct", sa.Float, nullable=False, server_default="0"),
            sa.Column("split_amount", sa.Float, nullable=False, server_default="0"),
            sa.Column("role", sa.String(50), nullable=True),
            sa.Column("notes", sa.String(500), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if "contact_merge_logs" not in tables:
        op.create_table(
            "contact_merge_logs",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("organization_id", sa.Integer, nullable=False, index=True),
            sa.Column("primary_contact_id", sa.Integer, nullable=False),
            sa.Column("merged_contact_id", sa.Integer, nullable=False),
            sa.Column("merged_by_user_id", sa.Integer, nullable=False),
            sa.Column("before_snapshot", sa.Text, nullable=True),
            sa.Column("after_snapshot", sa.Text, nullable=True),
            sa.Column("fields_changed", sa.String(500), nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="completed"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if "product_bundles" not in tables:
        op.create_table(
            "product_bundles",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("organization_id", sa.Integer, nullable=False, index=True),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("description", sa.Text, nullable=True),
            sa.Column("bundle_price", sa.Float, nullable=False, server_default="0"),
            sa.Column("individual_total", sa.Float, nullable=False, server_default="0"),
            sa.Column("discount_pct", sa.Float, nullable=False, server_default="0"),
            sa.Column("items_json", sa.Text, nullable=True),
            sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if "bundle_items" not in tables:
        op.create_table(
            "bundle_items",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("bundle_id", sa.Integer, nullable=False, index=True),
            sa.Column("product_id", sa.Integer, nullable=False),
            sa.Column("quantity", sa.Integer, nullable=False, server_default="1"),
            sa.Column("unit_price", sa.Float, nullable=False, server_default="0"),
        )

    if "forecast_rollups" not in tables:
        op.create_table(
            "forecast_rollups",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("organization_id", sa.Integer, nullable=False, index=True),
            sa.Column("period", sa.String(20), nullable=False),
            sa.Column("period_type", sa.String(20), nullable=False, server_default="monthly"),
            sa.Column("group_by", sa.String(50), nullable=False, server_default="team"),
            sa.Column("group_value", sa.String(100), nullable=False),
            sa.Column("committed", sa.Float, nullable=False, server_default="0"),
            sa.Column("best_case", sa.Float, nullable=False, server_default="0"),
            sa.Column("pipeline", sa.Float, nullable=False, server_default="0"),
            sa.Column("weighted_pipeline", sa.Float, nullable=False, server_default="0"),
            sa.Column("closed_won", sa.Float, nullable=False, server_default="0"),
            sa.Column("target", sa.Float, nullable=False, server_default="0"),
            sa.Column("attainment_pct", sa.Float, nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if "conversion_funnels" not in tables:
        op.create_table(
            "conversion_funnels",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("organization_id", sa.Integer, nullable=False, index=True),
            sa.Column("period", sa.String(20), nullable=False),
            sa.Column("period_type", sa.String(20), nullable=False, server_default="monthly"),
            sa.Column("from_stage", sa.String(50), nullable=False),
            sa.Column("to_stage", sa.String(50), nullable=False),
            sa.Column("entered_count", sa.Integer, nullable=False, server_default="0"),
            sa.Column("converted_count", sa.Integer, nullable=False, server_default="0"),
            sa.Column("conversion_rate", sa.Float, nullable=False, server_default="0"),
            sa.Column("avg_time_hours", sa.Float, nullable=False, server_default="0"),
            sa.Column("median_time_hours", sa.Float, nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    # ── Batch 20 ─────────────────────────────────────────────────────────

    if "revenue_goals" not in tables:
        op.create_table(
            "revenue_goals",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("scope", sa.String(30), nullable=False, server_default="team"),
            sa.Column("scope_id", sa.Integer, nullable=True),
            sa.Column("period", sa.String(20), nullable=False),
            sa.Column("period_type", sa.String(20), nullable=False, server_default="quarterly"),
            sa.Column("target_amount", sa.Float, nullable=False, server_default="0"),
            sa.Column("current_amount", sa.Float, nullable=False, server_default="0"),
            sa.Column("stretch_amount", sa.Float, nullable=False, server_default="0"),
            sa.Column("attainment_pct", sa.Float, nullable=False, server_default="0"),
            sa.Column("gap", sa.Float, nullable=False, server_default="0"),
            sa.Column("status", sa.String(20), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if "deal_dependencies" not in tables:
        op.create_table(
            "deal_dependencies",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("deal_id", sa.Integer, nullable=False),
            sa.Column("depends_on_deal_id", sa.Integer, nullable=False),
            sa.Column("dependency_type", sa.String(30), nullable=False, server_default="blocks"),
            sa.Column("is_resolved", sa.Boolean, nullable=False, server_default=sa.text("false")),
            sa.Column("notes", sa.Text, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        )

    if "contact_timeline_events" not in tables:
        op.create_table(
            "contact_timeline_events",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("contact_id", sa.Integer, nullable=False, index=True),
            sa.Column("event_type", sa.String(30), nullable=False),
            sa.Column("event_source", sa.String(50), nullable=True),
            sa.Column("title", sa.String(300), nullable=False),
            sa.Column("description", sa.Text, nullable=True),
            sa.Column("entity_type", sa.String(30), nullable=True),
            sa.Column("entity_id", sa.Integer, nullable=True),
            sa.Column("actor_user_id", sa.Integer, nullable=True),
            sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if "email_warmups" not in tables:
        op.create_table(
            "email_warmups",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("email_address", sa.String(254), nullable=False),
            sa.Column("domain", sa.String(200), nullable=False),
            sa.Column("daily_limit", sa.Integer, nullable=False, server_default="5"),
            sa.Column("current_daily", sa.Integer, nullable=False, server_default="0"),
            sa.Column("target_daily", sa.Integer, nullable=False, server_default="50"),
            sa.Column("ramp_increment", sa.Integer, nullable=False, server_default="2"),
            sa.Column("warmup_day", sa.Integer, nullable=False, server_default="1"),
            sa.Column("reputation_score", sa.Integer, nullable=False, server_default="50"),
            sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
            sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if "territory_assignments" not in tables:
        op.create_table(
            "territory_assignments",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("territory_id", sa.Integer, nullable=False),
            sa.Column("user_id", sa.Integer, nullable=False),
            sa.Column("role", sa.String(30), nullable=False, server_default="rep"),
            sa.Column("quota", sa.Float, nullable=False, server_default="0"),
            sa.Column("current_revenue", sa.Float, nullable=False, server_default="0"),
            sa.Column("deal_count", sa.Integer, nullable=False, server_default="0"),
            sa.Column("is_primary", sa.Boolean, nullable=False, server_default=sa.text("true")),
            sa.Column("assigned_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if "quote_approvals" not in tables:
        op.create_table(
            "quote_approvals",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("quote_id", sa.Integer, nullable=False),
            sa.Column("level", sa.Integer, nullable=False, server_default="1"),
            sa.Column("approver_user_id", sa.Integer, nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
            sa.Column("reason", sa.Text, nullable=True),
            sa.Column("requested_by_user_id", sa.Integer, nullable=False),
            sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if "win_loss_records" not in tables:
        op.create_table(
            "win_loss_records",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("deal_id", sa.Integer, nullable=False),
            sa.Column("outcome", sa.String(10), nullable=False),
            sa.Column("primary_reason", sa.String(200), nullable=False),
            sa.Column("secondary_reason", sa.String(200), nullable=True),
            sa.Column("competitor_id", sa.Integer, nullable=True),
            sa.Column("deal_amount", sa.Float, nullable=False, server_default="0"),
            sa.Column("sales_cycle_days", sa.Integer, nullable=False, server_default="0"),
            sa.Column("notes", sa.Text, nullable=True),
            sa.Column("recorded_by_user_id", sa.Integer, nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )


def downgrade() -> None:
    # Batch 20
    op.drop_table("win_loss_records")
    op.drop_table("quote_approvals")
    op.drop_table("territory_assignments")
    op.drop_table("email_warmups")
    op.drop_table("contact_timeline_events")
    op.drop_table("deal_dependencies")
    op.drop_table("revenue_goals")
    # Batch 19
    op.drop_table("conversion_funnels")
    op.drop_table("forecast_rollups")
    op.drop_table("bundle_items")
    op.drop_table("product_bundles")
    op.drop_table("contact_merge_logs")
    op.drop_table("deal_splits")
    op.drop_table("drip_step_events")
    op.drop_table("call_logs")
    # Batch 18
    op.drop_table("audit_entries")
    op.drop_table("feature_requests")
    op.drop_table("forecast_scenarios")
    op.drop_table("onboarding_checklists")
    op.drop_table("onboarding_templates")
    op.drop_table("lead_score_rules")
    op.drop_table("drip_enrollments")
    op.drop_table("drip_steps")
    op.drop_table("drip_campaigns")
    op.drop_table("subscriptions")
    op.drop_table("subscription_plans")
    # Batch 17
    op.drop_table("activity_goals")
    op.drop_table("stage_gate_overrides")
    op.drop_table("stage_gates")
    op.drop_table("dedup_rules")
    op.drop_table("leaderboard_entries")
    op.drop_table("signature_requests")
    op.drop_table("meeting_bookings")
    op.drop_table("availability_slots")
    op.drop_table("customer_health_scores")
