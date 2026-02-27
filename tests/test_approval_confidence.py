"""Tests for approval confidence scoring and auto-approve patterns."""
import pytest

from app.core.security import create_access_token


def _super_token() -> dict[str, str]:
    token = create_access_token(
        {
            "id": 1,
            "email": "ceo@org1.com",
            "role": "CEO",
            "org_id": 1,
            "token_version": 1,
        }
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_approval_request_creates_pattern_on_approve(client):
    """Approving a request creates / increments the pattern."""
    # Request an approval
    r = await client.post(
        "/api/v1/approvals/request",
        json={"organization_id": 1, "approval_type": "notify_team", "payload_json": {"channel": "ops"}},
    )
    assert r.status_code == 201
    approval_id = r.json()["id"]

    # Approve it
    r2 = await client.post(f"/api/v1/approvals/{approval_id}/approve", json={"note": ""})
    assert r2.status_code == 200

    # Pattern should exist now
    r3 = await client.get("/api/v1/approvals/approval-patterns")
    assert r3.status_code == 200
    patterns = r3.json()
    assert any(p["approval_type"] == "notify_team" and p["approved_count"] == 1 for p in patterns)


@pytest.mark.asyncio
async def test_confidence_score_increases_with_approvals(client):
    """Each approval bumps confidence toward 1.0."""
    for _ in range(3):
        r = await client.post(
            "/api/v1/approvals/request",
            json={"organization_id": 1, "approval_type": "tag_contact", "payload_json": {"tag": "hot-lead"}},
        )
        assert r.status_code == 201
        aid = r.json()["id"]
        await client.post(f"/api/v1/approvals/{aid}/approve", json={"note": ""})

    r = await client.get("/api/v1/approvals/approval-patterns")
    patterns = r.json()
    p = next((x for x in patterns if x["approval_type"] == "tag_contact"), None)
    assert p is not None
    assert p["approved_count"] == 3
    assert p["confidence_score"] > 0.0


@pytest.mark.asyncio
async def test_auto_approve_triggers_after_threshold(client):
    """After threshold approvals and enabling auto-approve, next request is auto-approved."""
    approval_type = "mark_task_reviewed"
    payload = {"task_id": 99}
    policy_patch = await client.patch(
        "/api/v1/admin/orgs/1/autonomy-policy",
        headers=_super_token(),
        json={"allow_auto_approval": True, "min_readiness_for_auto_approval": 0},
    )
    assert policy_patch.status_code == 200

    # Create + approve threshold times
    threshold = 3
    for _ in range(threshold):
        r = await client.post(
            "/api/v1/approvals/request",
            json={"organization_id": 1, "approval_type": approval_type, "payload_json": payload},
        )
        aid = r.json()["id"]
        await client.post(f"/api/v1/approvals/{aid}/approve", json={"note": ""})

    # Get pattern and enable auto-approve with threshold=3
    patterns = (await client.get("/api/v1/approvals/approval-patterns")).json()
    p = next(x for x in patterns if x["approval_type"] == approval_type)
    patch_r = await client.patch(
        f"/api/v1/approvals/approval-patterns/{p['id']}",
        json={"is_auto_approve_enabled": True, "auto_approve_threshold": threshold},
    )
    assert patch_r.status_code == 200
    body = patch_r.json()
    assert body["is_auto_approve_enabled"] is True

    # Next request should be auto-approved
    r2 = await client.post(
        "/api/v1/approvals/request",
        json={"organization_id": 1, "approval_type": approval_type, "payload_json": payload},
    )
    assert r2.status_code == 201
    body = r2.json()
    assert body["status"] == "approved"
    assert body["auto_approved_at"] is not None
    assert body["confidence_score"] is not None and body["confidence_score"] > 0


@pytest.mark.asyncio
async def test_risky_type_never_auto_approves(client):
    """Risky approval types are never auto-approved even with high confidence."""
    risky_type = "send_message"
    payload = {"to": "ceo@org1.com", "subject": "test"}

    for _ in range(10):
        r = await client.post(
            "/api/v1/approvals/request",
            json={"organization_id": 1, "approval_type": risky_type, "payload_json": payload},
        )
        assert r.status_code == 201
        body = r.json()
        # Must not be auto-approved
        assert body["status"] == "pending"
        assert body["auto_approved_at"] is None


@pytest.mark.asyncio
async def test_reject_increments_reject_count(client):
    """Rejecting an approval increments reject_count on the pattern."""
    r = await client.post(
        "/api/v1/approvals/request",
        json={"organization_id": 1, "approval_type": "close_deal", "payload_json": {"deal": "X"}},
    )
    aid = r.json()["id"]
    await client.post(f"/api/v1/approvals/{aid}/reject", json={"note": ""})

    patterns = (await client.get("/api/v1/approvals/approval-patterns")).json()
    p = next((x for x in patterns if x["approval_type"] == "close_deal"), None)
    assert p is not None
    assert p["reject_count"] == 1


@pytest.mark.asyncio
async def test_delete_pattern_resets_history(client):
    """Deleting a pattern removes it from the list."""
    r = await client.post(
        "/api/v1/approvals/request",
        json={"organization_id": 1, "approval_type": "reset_me", "payload_json": {}},
    )
    aid = r.json()["id"]
    await client.post(f"/api/v1/approvals/{aid}/approve", json={"note": ""})

    patterns = (await client.get("/api/v1/approvals/approval-patterns")).json()
    p = next(x for x in patterns if x["approval_type"] == "reset_me")

    del_r = await client.delete(f"/api/v1/approvals/approval-patterns/{p['id']}")
    assert del_r.status_code == 204

    patterns2 = (await client.get("/api/v1/approvals/approval-patterns")).json()
    assert not any(x["approval_type"] == "reset_me" for x in patterns2)


@pytest.mark.asyncio
async def test_autonomy_policy_can_disable_auto_approval(client):
    approval_type = "policy_auto_disabled"
    payload = {"ticket": "A-1"}

    seed = await client.post(
        "/api/v1/approvals/request",
        json={"organization_id": 1, "approval_type": approval_type, "payload_json": payload},
    )
    assert seed.status_code == 201
    seed_id = seed.json()["id"]
    seed_approve = await client.post(f"/api/v1/approvals/{seed_id}/approve", json={"note": ""})
    assert seed_approve.status_code == 200

    patterns = (await client.get("/api/v1/approvals/approval-patterns")).json()
    pattern = next(x for x in patterns if x["approval_type"] == approval_type)
    pattern_patch = await client.patch(
        f"/api/v1/approvals/approval-patterns/{pattern['id']}",
        json={"is_auto_approve_enabled": True, "auto_approve_threshold": 1},
    )
    assert pattern_patch.status_code == 200

    policy_patch = await client.patch(
        "/api/v1/admin/orgs/1/autonomy-policy",
        headers=_super_token(),
        json={"allow_auto_approval": False},
    )
    assert policy_patch.status_code == 200
    assert policy_patch.json()["allow_auto_approval"] is False

    candidate = await client.post(
        "/api/v1/approvals/request",
        json={"organization_id": 1, "approval_type": approval_type, "payload_json": payload},
    )
    assert candidate.status_code == 201
    body = candidate.json()
    assert body["status"] == "pending"
    assert body["auto_approved_at"] is None


@pytest.mark.asyncio
async def test_suggest_only_mode_blocks_yes_execute(client):
    policy_patch = await client.patch(
        "/api/v1/admin/orgs/1/autonomy-policy",
        headers=_super_token(),
        json={"current_mode": "suggest_only"},
    )
    assert policy_patch.status_code == 200

    req = await client.post(
        "/api/v1/approvals/request",
        json={
            "organization_id": 1,
            "approval_type": "send_message",
            "payload_json": {"to": "ops@org1.com", "subject": "Run"},
        },
    )
    assert req.status_code == 201
    approval_id = req.json()["id"]

    approve = await client.post(
        f"/api/v1/approvals/{approval_id}/approve",
        json={"note": "YES EXECUTE"},
        headers={"Idempotency-Key": "conf-suggest-only-1"},
    )
    assert approve.status_code == 409
