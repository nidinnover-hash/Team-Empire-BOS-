"""Tests for app/services/autonomy_policy.py and the admin API endpoints that expose it.

Covers:
  - GET/PATCH autonomy-policy endpoints
  - GET policy meta, rollout config, history
  - Rollback to prior version
  - Rollout config updates
  - Template listing and retrieval
  - Service-level evaluate_autonomy_modes, can_auto_approve, can_execute_post_approval
  - RBAC enforcement (non-super-admin gets 403)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from unittest.mock import AsyncMock

import pytest

from tests.conftest import _make_auth_headers

ORG_ID = 1
BASE = f"/api/v1/admin/orgs/{ORG_ID}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class _FakeMetric:
    name: str
    value: int


@dataclass
class _FakeReadinessReport:
    org_id: int
    org_name: str
    score: int
    status: Literal["ready", "watch", "blocked"]
    blockers: list[str]
    recommendations: list[str]
    metrics: list[_FakeMetric]


def _healthy_readiness(**overrides):
    """Return a fake readiness report with a high score and no blockers."""
    defaults = {
        "org_id": ORG_ID,
        "org_name": "Test Org",
        "score": 95,
        "status": "ready",
        "blockers": [],
        "recommendations": [],
        "metrics": [
            _FakeMetric("active_users", 3),
            _FakeMetric("connected_integrations", 4),
            _FakeMetric("stale_integrations", 0),
            _FakeMetric("pending_approvals_sla_breached", 0),
            _FakeMetric("unread_high_alerts", 0),
        ],
    }
    defaults.update(overrides)
    return _FakeReadinessReport(**defaults)


def _blocked_readiness(**overrides):
    """Return a fake readiness report with blockers and low score."""
    defaults = {
        "org_id": ORG_ID,
        "org_name": "Test Org",
        "score": 30,
        "status": "blocked",
        "blockers": ["No connected integrations."],
        "recommendations": [],
        "metrics": [
            _FakeMetric("active_users", 1),
            _FakeMetric("connected_integrations", 0),
            _FakeMetric("stale_integrations", 2),
            _FakeMetric("pending_approvals_sla_breached", 3),
            _FakeMetric("unread_high_alerts", 5),
        ],
    }
    defaults.update(overrides)
    return _FakeReadinessReport(**defaults)


# ===================================================================
# API endpoint tests (use `client` fixture)
# ===================================================================


@pytest.mark.asyncio
async def test_get_autonomy_policy_returns_defaults(client):
    """GET autonomy-policy returns default policy when no config record exists."""
    r = await client.get(f"{BASE}/autonomy-policy")
    assert r.status_code == 200
    body = r.json()
    assert body["current_mode"] == "approved_execution"
    assert body["allow_auto_approval"] is True
    assert body["min_readiness_for_auto_approval"] == 70
    assert body["min_readiness_for_approved_execution"] == 65
    assert body["min_readiness_for_autonomous"] == 90
    assert body["block_on_unread_high_alerts"] is True
    assert body["block_on_stale_integrations"] is True
    assert body["block_on_sla_breaches"] is True


@pytest.mark.asyncio
async def test_get_autonomy_rollout_returns_defaults(client):
    """GET autonomy-rollout returns default rollout config when none exists."""
    r = await client.get(f"{BASE}/autonomy-rollout")
    assert r.status_code == 200
    body = r.json()
    assert body["kill_switch"] is False
    assert body["pilot_org_ids"] == []
    assert body["max_actions_per_day"] == 250


@pytest.mark.asyncio
async def test_get_autonomy_policy_history_initially_empty(client):
    """GET history returns empty list when no updates have been made."""
    r = await client.get(f"{BASE}/autonomy-policy/history")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_patch_autonomy_policy_updates_and_returns(client):
    """PATCH autonomy-policy applies updates and returns the merged policy."""
    payload = {
        "current_mode": "suggest_only",
        "allow_auto_approval": False,
        "min_readiness_for_auto_approval": 85,
    }
    r = await client.patch(f"{BASE}/autonomy-policy", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["current_mode"] == "suggest_only"
    assert body["allow_auto_approval"] is False
    assert body["min_readiness_for_auto_approval"] == 85
    # Fields not in the patch should retain defaults
    assert body["min_readiness_for_approved_execution"] == 65
    assert body["min_readiness_for_autonomous"] == 90
    # Meta fields should be populated
    assert body["updated_by_user_id"] == 1
    assert body["updated_by_email"] == "ceo@org1.com"
    assert body["updated_at"] is not None


@pytest.mark.asyncio
async def test_patch_autonomy_policy_creates_version_history(client):
    """PATCH autonomy-policy should create a version history entry."""
    payload = {"current_mode": "autonomous"}
    r = await client.patch(f"{BASE}/autonomy-policy", json=payload)
    assert r.status_code == 200

    r2 = await client.get(f"{BASE}/autonomy-policy/history")
    assert r2.status_code == 200
    history = r2.json()
    assert len(history) >= 1
    latest = history[0]
    assert latest["version_id"]  # non-empty
    assert latest["policy"]["current_mode"] == "autonomous"
    assert latest["rollback_of_version_id"] is None


@pytest.mark.asyncio
async def test_get_history_after_multiple_updates(client):
    """Multiple PATCH calls should produce multiple history entries in reverse order."""
    await client.patch(f"{BASE}/autonomy-policy", json={"current_mode": "suggest_only"})
    await client.patch(f"{BASE}/autonomy-policy", json={"current_mode": "approved_execution"})
    await client.patch(f"{BASE}/autonomy-policy", json={"current_mode": "autonomous"})

    r = await client.get(f"{BASE}/autonomy-policy/history")
    assert r.status_code == 200
    history = r.json()
    assert len(history) >= 3
    # Most recent first
    assert history[0]["policy"]["current_mode"] == "autonomous"
    assert history[1]["policy"]["current_mode"] == "approved_execution"
    assert history[2]["policy"]["current_mode"] == "suggest_only"


@pytest.mark.asyncio
async def test_rollback_to_prior_version(client):
    """POST rollback should restore the policy to a previous version's state."""
    # Create a version with suggest_only
    await client.patch(f"{BASE}/autonomy-policy", json={"current_mode": "suggest_only"})
    r_hist = await client.get(f"{BASE}/autonomy-policy/history")
    v1_id = r_hist.json()[0]["version_id"]

    # Update to autonomous
    await client.patch(f"{BASE}/autonomy-policy", json={"current_mode": "autonomous"})

    # Verify current is autonomous
    r_cur = await client.get(f"{BASE}/autonomy-policy")
    assert r_cur.json()["current_mode"] == "autonomous"

    # Rollback to v1
    r_rollback = await client.post(f"{BASE}/autonomy-policy/rollback/{v1_id}")
    assert r_rollback.status_code == 200
    assert r_rollback.json()["current_mode"] == "suggest_only"

    # Verify current policy is now suggest_only
    r_after = await client.get(f"{BASE}/autonomy-policy")
    assert r_after.json()["current_mode"] == "suggest_only"

    # History should have a new entry with rollback_of_version_id set
    r_hist2 = await client.get(f"{BASE}/autonomy-policy/history")
    latest = r_hist2.json()[0]
    assert latest["rollback_of_version_id"] == v1_id
    assert latest["policy"]["current_mode"] == "suggest_only"


@pytest.mark.asyncio
async def test_rollback_nonexistent_version_returns_404(client):
    """Rollback to a version that does not exist should return 404."""
    r = await client.post(f"{BASE}/autonomy-policy/rollback/NONEXISTENT_VERSION_ID")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_patch_rollout_config(client):
    """PATCH autonomy-rollout applies updates to rollout config."""
    payload = {
        "kill_switch": True,
        "pilot_org_ids": [1, 2, 3],
        "max_actions_per_day": 500,
    }
    r = await client.patch(f"{BASE}/autonomy-rollout", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["kill_switch"] is True
    assert body["pilot_org_ids"] == [1, 2, 3]
    assert body["max_actions_per_day"] == 500

    # Verify GET returns updated values
    r2 = await client.get(f"{BASE}/autonomy-rollout")
    assert r2.status_code == 200
    assert r2.json()["kill_switch"] is True


@pytest.mark.asyncio
async def test_list_templates(client):
    """GET templates returns all three predefined templates."""
    r = await client.get(f"{BASE}/autonomy-policy/templates")
    assert r.status_code == 200
    templates = r.json()
    assert len(templates) == 3
    template_ids = {t["id"] for t in templates}
    assert template_ids == {"conservative", "balanced", "aggressive"}
    for t in templates:
        assert "label" in t
        assert "description" in t
        assert "policy" in t
        assert "current_mode" in t["policy"]


@pytest.mark.asyncio
async def test_apply_template(client):
    """POST templates/{id} applies the template policy and returns updated policy."""
    r = await client.post(f"{BASE}/autonomy-policy/templates/conservative")
    assert r.status_code == 200
    body = r.json()
    assert body["current_mode"] == "suggest_only"
    assert body["allow_auto_approval"] is False
    assert body["min_readiness_for_auto_approval"] == 90


@pytest.mark.asyncio
async def test_apply_nonexistent_template_returns_404(client):
    """POST templates/nonexistent should return 404."""
    r = await client.post(f"{BASE}/autonomy-policy/templates/nonexistent")
    assert r.status_code == 404


# ===================================================================
# RBAC tests
# ===================================================================


@pytest.mark.asyncio
async def test_non_super_admin_gets_403(client):
    """A STAFF user without is_super_admin should be denied access (403)."""
    staff_headers = _make_auth_headers(user_id=4, email="staff@org1.com", role="STAFF", org_id=1)
    r = await client.get(f"{BASE}/autonomy-policy", headers=staff_headers)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_manager_without_super_admin_gets_403(client):
    """A MANAGER user without is_super_admin should be denied access (403)."""
    manager_headers = _make_auth_headers(user_id=3, email="manager@org1.com", role="MANAGER", org_id=1)
    r = await client.get(f"{BASE}/autonomy-policy", headers=manager_headers)
    assert r.status_code == 403


# ===================================================================
# Direct service-level tests (use `db` fixture + monkeypatch)
# ===================================================================


@pytest.mark.asyncio
async def test_evaluate_autonomy_modes_healthy(db, monkeypatch):
    """evaluate_autonomy_modes with a healthy readiness report allows approved_execution."""
    from app.models.organization import Organization
    from app.services import autonomy_policy as ap

    fake_report = _healthy_readiness()
    monkeypatch.setattr(ap, "build_org_readiness_report", AsyncMock(return_value=fake_report))

    org = (await db.execute(__import__("sqlalchemy").select(Organization).where(Organization.id == ORG_ID))).scalar_one()
    result = await ap.evaluate_autonomy_modes(db, org=org)

    assert "suggest_only" in result["allowed_modes"]
    assert "approved_execution" in result["allowed_modes"]
    # With score=95 and default policy (min_readiness_for_autonomous=90, mode=approved_execution),
    # autonomous is denied because mode cap is approved_execution (rank 1 < rank 2)
    assert "autonomous" in result["denied_modes"]


@pytest.mark.asyncio
async def test_evaluate_autonomy_modes_blocked(db, monkeypatch):
    """evaluate_autonomy_modes with a blocked readiness report denies higher modes."""
    from app.models.organization import Organization
    from app.services import autonomy_policy as ap

    fake_report = _blocked_readiness()
    monkeypatch.setattr(ap, "build_org_readiness_report", AsyncMock(return_value=fake_report))

    org = (await db.execute(__import__("sqlalchemy").select(Organization).where(Organization.id == ORG_ID))).scalar_one()
    result = await ap.evaluate_autonomy_modes(db, org=org)

    assert "suggest_only" in result["allowed_modes"]
    assert "approved_execution" in result["denied_modes"]
    assert "autonomous" in result["denied_modes"]
    assert len(result["reasons"]) > 0


@pytest.mark.asyncio
async def test_evaluate_autonomy_modes_autonomous_allowed(db, monkeypatch):
    """evaluate_autonomy_modes allows autonomous when mode is autonomous and readiness is high."""
    from app.models.organization import Organization
    from app.services import autonomy_policy as ap

    # First set the policy mode to autonomous
    await ap.update_autonomy_policy(
        db,
        organization_id=ORG_ID,
        updates={"current_mode": "autonomous"},
        updated_by_user_id=1,
    )

    fake_report = _healthy_readiness(score=95)
    monkeypatch.setattr(ap, "build_org_readiness_report", AsyncMock(return_value=fake_report))

    org = (await db.execute(__import__("sqlalchemy").select(Organization).where(Organization.id == ORG_ID))).scalar_one()
    result = await ap.evaluate_autonomy_modes(db, org=org)

    assert "autonomous" in result["allowed_modes"]
    assert "approved_execution" in result["allowed_modes"]
    assert "suggest_only" in result["allowed_modes"]


@pytest.mark.asyncio
async def test_can_auto_approve_returns_true_when_allowed(db, monkeypatch):
    """can_auto_approve returns (True, '') when rollout and readiness allow it."""
    from app.models.organization import Organization
    from app.services import autonomy_policy as ap

    fake_report = _healthy_readiness()
    monkeypatch.setattr(ap, "build_org_readiness_report", AsyncMock(return_value=fake_report))

    org = (await db.execute(__import__("sqlalchemy").select(Organization).where(Organization.id == ORG_ID))).scalar_one()
    allowed, reason = await ap.can_auto_approve(db, org=org)
    assert allowed is True
    assert reason == ""


@pytest.mark.asyncio
async def test_can_auto_approve_blocked_by_kill_switch(db, monkeypatch):
    """can_auto_approve returns False when the kill switch is on."""
    from app.models.organization import Organization
    from app.services import autonomy_policy as ap

    # Enable kill switch
    await ap.update_rollout_config(
        db,
        organization_id=ORG_ID,
        updates={"kill_switch": True},
    )

    fake_report = _healthy_readiness()
    monkeypatch.setattr(ap, "build_org_readiness_report", AsyncMock(return_value=fake_report))

    org = (await db.execute(__import__("sqlalchemy").select(Organization).where(Organization.id == ORG_ID))).scalar_one()
    allowed, reason = await ap.can_auto_approve(db, org=org)
    assert allowed is False
    assert "kill switch" in reason.lower()


@pytest.mark.asyncio
async def test_can_auto_approve_blocked_by_policy_disabled(db, monkeypatch):
    """can_auto_approve returns False when allow_auto_approval is False."""
    from app.models.organization import Organization
    from app.services import autonomy_policy as ap

    # Disable auto-approval in policy
    await ap.update_autonomy_policy(
        db,
        organization_id=ORG_ID,
        updates={"allow_auto_approval": False},
        updated_by_user_id=1,
    )

    fake_report = _healthy_readiness()
    monkeypatch.setattr(ap, "build_org_readiness_report", AsyncMock(return_value=fake_report))

    org = (await db.execute(__import__("sqlalchemy").select(Organization).where(Organization.id == ORG_ID))).scalar_one()
    allowed, reason = await ap.can_auto_approve(db, org=org)
    assert allowed is False
    assert "disabled" in reason.lower()


@pytest.mark.asyncio
async def test_can_execute_post_approval_allowed(db, monkeypatch):
    """can_execute_post_approval returns (True, '') when mode >= approved_execution."""
    from app.models.organization import Organization
    from app.services import autonomy_policy as ap

    org = (await db.execute(__import__("sqlalchemy").select(Organization).where(Organization.id == ORG_ID))).scalar_one()
    # Default mode is approved_execution so should be allowed
    allowed, reason = await ap.can_execute_post_approval(db, org=org)
    assert allowed is True
    assert reason == ""


@pytest.mark.asyncio
async def test_can_execute_post_approval_denied_suggest_only(db, monkeypatch):
    """can_execute_post_approval returns False when mode is suggest_only."""
    from app.models.organization import Organization
    from app.services import autonomy_policy as ap

    # Set mode to suggest_only
    await ap.update_autonomy_policy(
        db,
        organization_id=ORG_ID,
        updates={"current_mode": "suggest_only"},
        updated_by_user_id=1,
    )

    org = (await db.execute(__import__("sqlalchemy").select(Organization).where(Organization.id == ORG_ID))).scalar_one()
    allowed, reason = await ap.can_execute_post_approval(db, org=org)
    assert allowed is False
    assert "denied" in reason.lower()
