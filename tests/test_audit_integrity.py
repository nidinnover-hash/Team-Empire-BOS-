"""Tests for immutable audit ledger — HMAC chain signing and verification."""
import pytest

from app.core.audit_integrity import compute_event_signature, verify_chain
from app.schemas.event import EventCreate
from app.services import event as event_service

# ── Signature computation ────────────────────────────────────────────────────


def test_signature_is_deterministic():
    from datetime import UTC, datetime

    ts = datetime(2026, 3, 6, 12, 0, 0, tzinfo=UTC)
    sig1 = compute_event_signature(1, 1, "test", ts, {"key": "val"}, None)
    sig2 = compute_event_signature(1, 1, "test", ts, {"key": "val"}, None)
    assert sig1 == sig2
    assert len(sig1) == 64  # SHA-256 hex digest


def test_signature_changes_with_different_payload():
    from datetime import UTC, datetime

    ts = datetime(2026, 3, 6, 12, 0, 0, tzinfo=UTC)
    sig1 = compute_event_signature(1, 1, "test", ts, {"key": "a"}, None)
    sig2 = compute_event_signature(1, 1, "test", ts, {"key": "b"}, None)
    assert sig1 != sig2


def test_signature_changes_with_prev_hash():
    from datetime import UTC, datetime

    ts = datetime(2026, 3, 6, 12, 0, 0, tzinfo=UTC)
    sig1 = compute_event_signature(1, 1, "test", ts, {}, None)
    sig2 = compute_event_signature(1, 1, "test", ts, {}, "abc123")
    assert sig1 != sig2


# ── Event signing integration ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_log_event_adds_signature(db):
    event = await event_service.log_event(
        db,
        EventCreate(
            organization_id=1,
            event_type="test_signed",
            payload_json={"action": "test"},
        ),
    )
    assert event.signature is not None
    assert len(event.signature) == 64


@pytest.mark.asyncio
async def test_second_event_chains_prev_hash(db):
    e1 = await event_service.log_event(
        db,
        EventCreate(
            organization_id=1,
            event_type="chain_test_1",
            payload_json={},
        ),
    )
    e2 = await event_service.log_event(
        db,
        EventCreate(
            organization_id=1,
            event_type="chain_test_2",
            payload_json={},
        ),
    )
    assert e2.prev_hash == e1.signature


# ── Chain verification ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_verify_chain_valid(db):
    for i in range(3):
        await event_service.log_event(
            db,
            EventCreate(
                organization_id=1,
                event_type=f"verify_test_{i}",
                payload_json={"index": i},
            ),
        )
    result = await verify_chain(db, organization_id=1)
    assert result["valid"] is True
    assert result["checked"] >= 3
    assert result["first_broken_id"] is None


@pytest.mark.asyncio
async def test_verify_chain_empty(db):
    result = await verify_chain(db, organization_id=999)
    assert result["valid"] is True
    assert result["checked"] == 0


# ── DELETE guard ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_event_delete_blocked(db):
    event = await event_service.log_event(
        db,
        EventCreate(
            organization_id=1,
            event_type="immutable_test",
            payload_json={},
        ),
    )
    with pytest.raises(PermissionError, match="immutable"):
        await db.delete(event)
        await db.flush()


# ── Admin verify endpoint ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_verify_endpoint(client):
    # Log some events first
    await client.post("/api/v1/contacts", json={"name": "Audit Test Contact"})

    resp = await client.get("/api/v1/admin/audit/verify")
    assert resp.status_code == 200
    data = resp.json()
    assert "valid" in data
    assert "checked" in data
