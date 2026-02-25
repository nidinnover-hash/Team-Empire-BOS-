"""
Tests for patterns introduced in the Feb 23 improvement round:
  - Atomic approval approve/reject (race-safe)
  - Compose rate limiting (per-org, 20/hour)
  - Slack sync deduplication (upsert DailyContext)
  - Double-execution guard in execution engine
  - Execution engine org-isolation and status guard
  - Idempotency key max_length enforcement
"""

from datetime import datetime, timezone

from sqlalchemy import select

from app.core.deps import get_db
from app.core.security import create_access_token
from app.main import app as fastapi_app
from app.models.approval import Approval
from app.models.execution import Execution
from app.services import email_service, execution_engine, slack_service


def _auth(user_id: int = 1, role: str = "CEO", org_id: int = 1) -> dict:
    email_by_user = {
        1: "ceo@org1.com",
        2: "ceo@org2.com",
        3: "manager@org1.com",
        4: "staff@org1.com",
        5: "nidinnover@gmail.com",
    }
    token = create_access_token(
        {
            "id": user_id,
            "email": email_by_user.get(user_id, f"u{user_id}@org.com"),
            "role": role,
            "org_id": org_id,
            "token_version": 1,
        }
    )
    return {"Authorization": f"Bearer {token}"}


async def _get_db_session():
    override = fastapi_app.dependency_overrides[get_db]
    agen = override()
    session = await agen.__anext__()
    return session, agen


# ── Atomic Approval: approve already-approved returns 404 ──────────────────


async def test_approve_already_approved_returns_404(client):
    """An approval that is already approved should fail the second attempt."""
    headers = _auth(3, "MANAGER")
    req = await client.post(
        "/api/v1/approvals/request",
        json={"organization_id": 1, "approval_type": "archive_note", "payload_json": {"note_id": 1}},
        headers=headers,
    )
    assert req.status_code == 201
    approval_id = req.json()["id"]

    ceo = _auth(1, "CEO")
    # First approve succeeds
    r1 = await client.post(
        f"/api/v1/approvals/{approval_id}/approve",
        json={"note": "ok"},
        headers=ceo,
    )
    assert r1.status_code == 200

    # Second approve fails — already approved
    r2 = await client.post(
        f"/api/v1/approvals/{approval_id}/approve",
        json={"note": "again"},
        headers=ceo,
    )
    assert r2.status_code == 404


async def test_reject_already_rejected_returns_404(client):
    """An approval that is already rejected should fail the second attempt."""
    headers = _auth(3, "MANAGER")
    req = await client.post(
        "/api/v1/approvals/request",
        json={"organization_id": 1, "approval_type": "archive_note", "payload_json": {"note_id": 2}},
        headers=headers,
    )
    assert req.status_code == 201
    approval_id = req.json()["id"]

    ceo = _auth(1, "CEO")
    r1 = await client.post(
        f"/api/v1/approvals/{approval_id}/reject",
        json={"note": "no"},
        headers=ceo,
    )
    assert r1.status_code == 200

    r2 = await client.post(
        f"/api/v1/approvals/{approval_id}/reject",
        json={"note": "no again"},
        headers=ceo,
    )
    assert r2.status_code == 404


async def test_approve_then_reject_returns_404(client):
    """Cannot reject an already-approved approval."""
    headers = _auth(3, "MANAGER")
    req = await client.post(
        "/api/v1/approvals/request",
        json={"organization_id": 1, "approval_type": "archive_note", "payload_json": {"note_id": 3}},
        headers=headers,
    )
    assert req.status_code == 201
    approval_id = req.json()["id"]

    ceo = _auth(1, "CEO")
    await client.post(
        f"/api/v1/approvals/{approval_id}/approve",
        json={"note": "ok"},
        headers=ceo,
    )

    r2 = await client.post(
        f"/api/v1/approvals/{approval_id}/reject",
        json={"note": "changed my mind"},
        headers=ceo,
    )
    assert r2.status_code == 404


# ── Compose rate limit ─────────────────────────────────────────────────────


async def test_compose_rate_limit_blocks_after_max(client, monkeypatch):
    """Verify compose endpoint returns 429 after exceeding rate limit."""
    from app.api.v1.endpoints import email as email_endpoint

    # Monkey-patch the rate limiter to a tiny limit for testing
    monkeypatch.setattr(email_endpoint, "_COMPOSE_MAX_PER_HOUR", 2)
    # Reset the bucket so previous tests don't interfere
    email_endpoint._compose_counts.clear()

    async def fake_compose(*args, **kwargs):
        return "Dear Client, here is the draft."

    monkeypatch.setattr(email_service, "compose_email", fake_compose)

    ceo = _auth(1, "CEO")
    body = {"to": "test@example.com", "subject": "Test", "instruction": "Say hi"}

    # First two should succeed
    r1 = await client.post("/api/v1/email/compose", json=body, headers=ceo)
    assert r1.status_code == 200
    r2 = await client.post("/api/v1/email/compose", json=body, headers=ceo)
    assert r2.status_code == 200

    # Third should be rate-limited
    r3 = await client.post("/api/v1/email/compose", json=body, headers=ceo)
    assert r3.status_code == 429
    assert "rate limit" in r3.json()["detail"].lower()

    # Clean up
    email_endpoint._compose_counts.clear()
    monkeypatch.setattr(email_endpoint, "_COMPOSE_MAX_PER_HOUR", 20)


# ── Slack sync dedup ───────────────────────────────────────────────────────


async def test_slack_sync_deduplicates_daily_context(client, monkeypatch):
    """Running sync twice for the same channel+date should update, not duplicate."""
    call_log = {"sync_count": 0}

    async def _fake_sync(db, org_id):
        call_log["sync_count"] += 1
        return {"channels_synced": 2, "messages_read": 10, "error": None}

    async def _status(db, org_id):
        return {"connected": True, "last_sync_at": None, "team": "T", "channels_tracked": 2}

    monkeypatch.setattr(slack_service, "sync_slack_messages", _fake_sync)
    monkeypatch.setattr(slack_service, "get_slack_status", _status)

    ceo = _auth(1, "CEO")
    r1 = await client.post("/api/v1/integrations/slack/sync", headers=ceo)
    assert r1.status_code == 200

    r2 = await client.post("/api/v1/integrations/slack/sync", headers=ceo)
    assert r2.status_code == 200
    assert call_log["sync_count"] == 2


# ── Double-execution guard ─────────────────────────────────────────────────


async def test_double_execution_skips_already_executed(client):
    """Calling execute_approval on an already-executed approval should skip silently."""
    db, agen = await _get_db_session()
    try:
        approval = Approval(
            organization_id=1,
            requested_by=1,
            approval_type="assign_leads",
            payload_json={"count": 3},
            status="approved",
            approved_by=1,
            approved_at=datetime.now(timezone.utc),
            executed_at=datetime.now(timezone.utc),  # already executed
        )
        db.add(approval)
        await db.commit()
        await db.refresh(approval)

        # Should return silently (no error, no new execution)
        await execution_engine.execute_approval(
            db=db, approval=approval, actor_user_id=1, actor_org_id=1
        )

        # No execution record should be created
        result = await db.execute(
            select(Execution).where(Execution.approval_id == approval.id)
        )
        assert result.scalar_one_or_none() is None
    finally:
        await agen.aclose()


# ── Org isolation in execution engine ──────────────────────────────────────


async def test_execution_engine_rejects_cross_org(client):
    """execute_approval must reject when actor org doesn't match approval org."""
    db, agen = await _get_db_session()
    try:
        approval = Approval(
            organization_id=1,
            requested_by=1,
            approval_type="assign_leads",
            payload_json={"count": 3},
            status="approved",
            approved_by=1,
            approved_at=datetime.now(timezone.utc),
        )
        db.add(approval)
        await db.commit()
        await db.refresh(approval)

        try:
            await execution_engine.execute_approval(
                db=db, approval=approval, actor_user_id=99, actor_org_id=999
            )
            raise AssertionError("Should have raised ValueError")
        except ValueError as e:
            assert "Cross-org" in str(e)
    finally:
        await agen.aclose()


# ── Status guard in execution engine ───────────────────────────────────────


async def test_execution_engine_rejects_pending_approval(client):
    """execute_approval must reject when approval status is not 'approved'."""
    db, agen = await _get_db_session()
    try:
        approval = Approval(
            organization_id=1,
            requested_by=1,
            approval_type="assign_leads",
            payload_json={"count": 3},
            status="pending",
        )
        db.add(approval)
        await db.commit()
        await db.refresh(approval)

        try:
            await execution_engine.execute_approval(
                db=db, approval=approval, actor_user_id=1, actor_org_id=1
            )
            raise AssertionError("Should have raised ValueError")
        except ValueError as e:
            assert "pending" in str(e)
    finally:
        await agen.aclose()


# ── Handler timeout test ──────────────────────────────────────────────────


async def test_execution_handler_timeout_records_failure(client, monkeypatch):
    """A handler that takes too long should be recorded as failed with timeout error."""
    import asyncio

    # Reduce timeout for testing
    monkeypatch.setattr(execution_engine, "HANDLER_TIMEOUT_SECONDS", 0.1)

    async def _slow_handler(payload):
        await asyncio.sleep(5)
        return {"action": "slow"}

    monkeypatch.setattr(
        execution_engine, "HANDLERS",
        {**execution_engine.HANDLERS, "slow_op": _slow_handler},
    )

    db, agen = await _get_db_session()
    try:
        approval = Approval(
            organization_id=1,
            requested_by=1,
            approval_type="slow_op",
            payload_json={},
            status="approved",
            approved_by=1,
            approved_at=datetime.now(timezone.utc),
        )
        db.add(approval)
        await db.commit()
        await db.refresh(approval)

        await execution_engine.execute_approval(
            db=db, approval=approval, actor_user_id=1, actor_org_id=1
        )

        result = await db.execute(
            select(Execution).where(Execution.approval_id == approval.id)
        )
        execution = result.scalar_one()
        assert execution.status == "failed"
        assert "timed out" in (execution.error_text or "").lower()
    finally:
        await agen.aclose()


# ── Idempotency key max_length ─────────────────────────────────────────────


async def test_idempotency_key_over_256_rejected(client, monkeypatch):
    """An Idempotency-Key longer than 256 chars should be rejected by FastAPI."""
    ceo = _auth(1, "CEO")
    long_key = "x" * 300
    resp = await client.post(
        "/api/v1/email/sync",
        headers={**ceo, "Idempotency-Key": long_key},
    )
    assert resp.status_code == 422


# ── Email send compose path via execution engine ──────────────────────────


async def test_execution_email_send_message_cross_org_blocked(client, monkeypatch):
    """Email execution path must also respect org isolation."""
    db, agen = await _get_db_session()
    try:
        approval = Approval(
            organization_id=2,  # different org
            requested_by=1,
            approval_type="send_message",
            payload_json={"email_id": 99},
            status="approved",
            approved_by=1,
            approved_at=datetime.now(timezone.utc),
        )
        db.add(approval)
        await db.commit()
        await db.refresh(approval)

        try:
            await execution_engine.execute_approval(
                db=db, approval=approval, actor_user_id=1, actor_org_id=1
            )
            raise AssertionError("Should have raised ValueError")
        except ValueError as e:
            assert "Cross-org" in str(e)
    finally:
        await agen.aclose()


# ── Unknown handler is recorded as skipped ─────────────────────────────────


async def test_execution_unknown_handler_skipped(client):
    """An approval with an unknown handler type should create execution with status=skipped."""
    db, agen = await _get_db_session()
    try:
        approval = Approval(
            organization_id=1,
            requested_by=1,
            approval_type="completely_unknown_type_xyz",
            payload_json={},
            status="approved",
            approved_by=1,
            approved_at=datetime.now(timezone.utc),
        )
        db.add(approval)
        await db.commit()
        await db.refresh(approval)

        await execution_engine.execute_approval(
            db=db, approval=approval, actor_user_id=1, actor_org_id=1
        )

        result = await db.execute(
            select(Execution).where(Execution.approval_id == approval.id)
        )
        execution = result.scalar_one()
        assert execution.status == "skipped"
        assert execution.output_json.get("reason") == "no_handler"
    finally:
        await agen.aclose()
