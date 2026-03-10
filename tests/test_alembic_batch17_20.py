"""Tests for Alembic migration completeness for batches 17-20."""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest


MIGRATION_PATH = Path("alembic/versions/20260310_0087_add_batch_17_18_19_20_tables.py")


@pytest.fixture(scope="module")
def migration_module():
    spec = importlib.util.spec_from_file_location("migration_0087", str(MIGRATION_PATH))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migration_file_exists():
    assert MIGRATION_PATH.exists(), f"Migration file not found: {MIGRATION_PATH}"


def test_migration_revision_chain(migration_module):
    assert migration_module.revision == "20260310_0087"
    assert migration_module.down_revision == "20260310_0086"


def test_migration_has_upgrade_and_downgrade(migration_module):
    assert hasattr(migration_module, "upgrade")
    assert hasattr(migration_module, "downgrade")
    assert callable(migration_module.upgrade)
    assert callable(migration_module.downgrade)


def test_migration_create_table_count():
    content = MIGRATION_PATH.read_text(encoding="utf-8")
    tables_up = re.findall(r'op\.create_table\(\s*"([^"]+)"', content)
    assert len(tables_up) >= 28, f"Expected at least 28 tables, found {len(tables_up)}: {tables_up}"


def test_migration_downgrade_drops_all_created_tables():
    content = MIGRATION_PATH.read_text(encoding="utf-8")
    tables_up = set(re.findall(r'op\.create_table\(\s*"([^"]+)"', content))
    tables_down = set(re.findall(r'op\.drop_table\("([^"]+)"\)', content))
    missing = tables_up - tables_down
    assert not missing, f"Tables created but not dropped in downgrade: {missing}"


def test_migration_covers_batch17_tables():
    content = MIGRATION_PATH.read_text(encoding="utf-8")
    batch17 = ["customer_health_scores", "availability_slots", "meeting_bookings",
                "signature_requests", "leaderboard_entries", "dedup_rules",
                "stage_gates", "activity_goals"]
    for table in batch17:
        assert table in content, f"Batch 17 table missing: {table}"


def test_migration_covers_batch18_tables():
    content = MIGRATION_PATH.read_text(encoding="utf-8")
    batch18 = ["subscription_plans", "subscriptions", "drip_campaigns",
                "lead_score_rules", "onboarding_templates", "forecast_scenarios",
                "feature_requests", "audit_entries"]
    for table in batch18:
        assert table in content, f"Batch 18 table missing: {table}"


def test_migration_covers_batch19_tables():
    content = MIGRATION_PATH.read_text(encoding="utf-8")
    batch19 = ["call_logs", "deal_splits", "contact_merge_logs",
                "product_bundles", "bundle_items", "forecast_rollups", "conversion_funnels"]
    for table in batch19:
        assert table in content, f"Batch 19 table missing: {table}"


def test_migration_covers_batch20_tables():
    content = MIGRATION_PATH.read_text(encoding="utf-8")
    batch20 = ["revenue_goals", "deal_dependencies", "contact_timeline_events",
                "email_warmups", "territory_assignments", "quote_approvals", "win_loss_records"]
    for table in batch20:
        assert table in content, f"Batch 20 table missing: {table}"


def test_downgrade_respects_foreign_key_order():
    """Tables with FK dependencies should be dropped before their parents."""
    content = MIGRATION_PATH.read_text(encoding="utf-8")
    # Find drop order
    drops = re.findall(r'op\.drop_table\("([^"]+)"\)', content)

    # stage_gate_overrides depends on stage_gates
    if "stage_gate_overrides" in drops and "stage_gates" in drops:
        assert drops.index("stage_gate_overrides") < drops.index("stage_gates")

    # subscriptions depends on subscription_plans
    if "subscriptions" in drops and "subscription_plans" in drops:
        assert drops.index("subscriptions") < drops.index("subscription_plans")

    # onboarding_checklists depends on onboarding_templates
    if "onboarding_checklists" in drops and "onboarding_templates" in drops:
        assert drops.index("onboarding_checklists") < drops.index("onboarding_templates")
