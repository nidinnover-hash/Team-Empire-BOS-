"""Tests for /api/v1/approvals endpoints."""
from datetime import datetime, timezone

from app.models.approval import Approval

from app.core.deps import get_db
from app.main import app as fastapi_app


async def _get_session():
    override = fastapi_app.dependency_overrides[get_db]
    agen = override()
    session = await agen.__anext__()
    return session, agen


async def _seed_approval(client, **overrides):
    session, agen = await _get_session()
    try:
        _status = overrides.get("status", "pending")
        approval = Approval(
            organization_id=overrides.get("organization_id", 1),
            requested_by=overrides.get("requested_by", 1),
            approval_type=overrides.get("approval_type", "task_execution"),
            payload_json=overrides.get("payload_json", {}),
            status=_status,
            approved_by=overrides.get("approved_by", 1 if _status == "approved" else None),
            created_at=datetime.now(timezone.utc),
        )
        session.add(approval)
        await session.commit()
        return approval.id
    finally:
        await agen.aclose()


async def test_request_approval_returns_201(client):
    resp = await client.post(
        "/api/v1/approvals/request",
        json={"approval_type": "task_execution", "payload_json": {"task": "test"}},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["approval_type"] == "task_execution"
    assert body["status"] == "pending"


async def test_list_approvals_empty(client):
    resp = await client.get("/api/v1/approvals")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_approvals_with_status_filter(client):
    await _seed_approval(client)
    resp = await client.get("/api/v1/approvals?status=pending")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) >= 1
    assert all(a["status"] == "pending" for a in items)


async def test_approve_changes_status(client):
    aid = await _seed_approval(client)
    resp = await client.post(f"/api/v1/approvals/{aid}/approve", json={"note": "ok"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"


async def test_approve_nonexistent_returns_404(client):
    resp = await client.post("/api/v1/approvals/99999/approve", json={"note": "ok"})
    assert resp.status_code == 404


async def test_reject_changes_status(client):
    aid = await _seed_approval(client)
    resp = await client.post(f"/api/v1/approvals/{aid}/reject", json={"note": "no"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"


async def test_reject_already_approved_returns_404(client):
    aid = await _seed_approval(client, status="approved")
    resp = await client.post(f"/api/v1/approvals/{aid}/reject", json={"note": "no"})
    assert resp.status_code == 404


async def test_timeline_returns_shape(client):
    await _seed_approval(client)
    resp = await client.get("/api/v1/approvals/timeline")
    assert resp.status_code == 200
    body = resp.json()
    assert "pending_count" in body
    assert "approved_count" in body
    assert "items" in body
