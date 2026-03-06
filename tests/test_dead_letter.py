"""Tests for the dead-letter queue system — capture, inspect, retry, archive, and API."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.core.security import create_access_token
from app.models.dead_letter import DeadLetterEntry
from app.platform.dead_letter.inspector import (
    count_by_source_type,
    count_by_status,
    get_entry,
    list_entries,
)
from app.platform.dead_letter.reprocessor import (
    archive_entry,
    archive_old_entries,
    resolve_entry,
    retry_entry,
)
from app.platform.dead_letter.store import capture_failure


def _ceo_headers(org_id: int = 1) -> dict:
    token = create_access_token({"id": 1, "email": "ceo@org1.com", "role": "CEO", "org_id": org_id, "token_version": 1})
    return {"Authorization": f"Bearer {token}"}


def _staff_headers(org_id: int = 1) -> dict:
    token = create_access_token({"id": 4, "email": "staff@org1.com", "role": "STAFF", "org_id": org_id, "token_version": 1})
    return {"Authorization": f"Bearer {token}"}


def _manager_headers(org_id: int = 1) -> dict:
    token = create_access_token({"id": 3, "email": "mgr@org1.com", "role": "MANAGER", "org_id": org_id, "token_version": 1})
    return {"Authorization": f"Bearer {token}"}


async def _seed_dead_letter(client, *, source_type="webhook", source_id="1", error_message=None) -> int:
    """Insert a dead-letter entry through the client's DB session.

    Returns the entry ID. Works without needing a separate db fixture.
    """
    from sqlalchemy import text

    from app.core.deps import get_db
    from app.main import app as fastapi_app

    override = fastapi_app.dependency_overrides.get(get_db)
    assert override is not None, "client fixture must be active"
    async for session in override():
        result = await session.execute(
            text(
                "INSERT INTO dead_letter_entries "
                "(organization_id, source_type, source_id, error_message, payload, status, attempts, max_attempts, created_at) "
                "VALUES (:org, :st, :sid, :err, '{}', 'pending', 1, 3, datetime('now'))"
            ),
            {"org": 1, "st": source_type, "sid": source_id, "err": error_message},
        )
        await session.commit()
        return result.lastrowid  # type: ignore[return-value]
    raise RuntimeError("Failed to seed dead-letter entry")


# ── Store: capture_failure ────────────────────────────────────────────────────

async def test_capture_failure_creates_entry(db):
    entry = await capture_failure(
        db,
        organization_id=1,
        source_type="webhook",
        source_id="42",
        source_detail="https://hooks.example.com/callback",
        payload={"event": "order.created", "endpoint_id": 7},
        error_message="HTTP 502",
        error_type="webhook_delivery_exhausted",
    )
    assert entry is not None
    assert entry.organization_id == 1
    assert entry.source_type == "webhook"
    assert entry.source_id == "42"
    assert entry.status == "pending"
    assert entry.error_message == "HTTP 502"
    assert entry.attempts == 1


async def test_capture_failure_returns_none_when_disabled(db, monkeypatch):
    monkeypatch.setattr("app.platform.dead_letter.store.settings.DEAD_LETTER_ENABLED", False)
    entry = await capture_failure(
        db,
        organization_id=1,
        source_type="scheduler",
        source_id="token_health_check",
    )
    assert entry is None


async def test_capture_failure_never_raises(db, monkeypatch):
    """capture_failure should swallow exceptions gracefully."""
    # Break the DB session to force an error
    async def broken_commit(*_a, **_kw):
        raise RuntimeError("DB down")

    monkeypatch.setattr(db, "commit", broken_commit)
    entry = await capture_failure(
        db,
        organization_id=1,
        source_type="scheduler",
        source_id="broken_job",
        error_message="RuntimeError: DB down",
    )
    assert entry is None


# ── Inspector: list, get, count ───────────────────────────────────────────────

async def test_list_entries_empty(db):
    items = await list_entries(db, organization_id=1)
    assert items == []


async def test_list_entries_filtered_by_status(db):
    await capture_failure(db, organization_id=1, source_type="webhook", source_id="1")
    await capture_failure(db, organization_id=1, source_type="scheduler", source_id="2")
    all_items = await list_entries(db, organization_id=1)
    assert len(all_items) == 2

    webhook_items = await list_entries(db, organization_id=1, source_type="webhook")
    assert len(webhook_items) == 1
    assert webhook_items[0].source_type == "webhook"


async def test_list_entries_org_isolation(db):
    await capture_failure(db, organization_id=1, source_type="webhook", source_id="1")
    await capture_failure(db, organization_id=2, source_type="webhook", source_id="2")
    org1 = await list_entries(db, organization_id=1)
    org2 = await list_entries(db, organization_id=2)
    assert len(org1) == 1
    assert len(org2) == 1
    assert org1[0].source_id == "1"
    assert org2[0].source_id == "2"


async def test_get_entry(db):
    entry = await capture_failure(db, organization_id=1, source_type="workflow", source_id="99")
    assert entry is not None
    fetched = await get_entry(db, entry.id, organization_id=1)
    assert fetched is not None
    assert fetched.id == entry.id


async def test_get_entry_wrong_org(db):
    entry = await capture_failure(db, organization_id=1, source_type="workflow", source_id="99")
    assert entry is not None
    fetched = await get_entry(db, entry.id, organization_id=2)
    assert fetched is None


async def test_count_by_status(db):
    await capture_failure(db, organization_id=1, source_type="webhook", source_id="1")
    await capture_failure(db, organization_id=1, source_type="webhook", source_id="2")
    counts = await count_by_status(db, organization_id=1)
    assert counts.get("pending", 0) == 2


async def test_count_by_source_type(db):
    await capture_failure(db, organization_id=1, source_type="webhook", source_id="1")
    await capture_failure(db, organization_id=1, source_type="scheduler", source_id="2")
    await capture_failure(db, organization_id=1, source_type="scheduler", source_id="3")
    counts = await count_by_source_type(db, organization_id=1)
    assert counts.get("webhook") == 1
    assert counts.get("scheduler") == 2


# ── Reprocessor: retry, resolve, archive ──────────────────────────────────────

async def test_retry_entry_increments_attempts(db):
    entry = await capture_failure(db, organization_id=1, source_type="webhook", source_id="1")
    assert entry is not None
    retried = await retry_entry(db, entry.id, organization_id=1)
    assert retried is not None
    assert retried.status == "retrying"
    assert retried.attempts == 2


async def test_retry_resolved_entry_is_noop(db):
    entry = await capture_failure(db, organization_id=1, source_type="webhook", source_id="1")
    assert entry is not None
    await resolve_entry(db, entry.id, organization_id=1)
    retried = await retry_entry(db, entry.id, organization_id=1)
    assert retried is not None
    assert retried.status == "resolved"  # not changed


async def test_resolve_entry(db):
    entry = await capture_failure(db, organization_id=1, source_type="scheduler", source_id="job1")
    assert entry is not None
    resolved = await resolve_entry(db, entry.id, organization_id=1, actor_user_id=1)
    assert resolved is not None
    assert resolved.status == "resolved"
    assert resolved.resolved_at is not None
    assert resolved.resolved_by == 1


async def test_archive_entry(db):
    entry = await capture_failure(db, organization_id=1, source_type="webhook", source_id="1")
    assert entry is not None
    archived = await archive_entry(db, entry.id, organization_id=1)
    assert archived is not None
    assert archived.status == "archived"
    assert archived.resolved_at is not None


async def test_archive_old_entries(db):
    # Create an entry and backdate it
    entry = await capture_failure(db, organization_id=1, source_type="webhook", source_id="old")
    assert entry is not None
    entry.created_at = datetime.now(UTC) - timedelta(days=45)
    await db.commit()

    # Also create a fresh entry
    await capture_failure(db, organization_id=1, source_type="webhook", source_id="fresh")

    count = await archive_old_entries(db, organization_id=1, days=30)
    assert count == 1

    # Fresh entry should still be pending
    items = await list_entries(db, organization_id=1, status="pending")
    assert len(items) == 1
    assert items[0].source_id == "fresh"


# ── API Endpoints ─────────────────────────────────────────────────────────────

async def test_api_list_dead_letter_empty(client):
    resp = await client.get("/api/v1/control/dead-letter", headers=_ceo_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 0
    assert body["items"] == []


async def test_api_list_dead_letter_with_entries(client):
    await _seed_dead_letter(client, source_type="webhook", source_id="1", error_message="HTTP 500")
    await _seed_dead_letter(client, source_type="scheduler", source_id="job1", error_message="Timeout")

    resp = await client.get("/api/v1/control/dead-letter", headers=_ceo_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 2
    assert len(body["items"]) == 2


async def test_api_list_dead_letter_filter_by_source_type(client):
    await _seed_dead_letter(client, source_type="webhook", source_id="1")
    await _seed_dead_letter(client, source_type="scheduler", source_id="2")

    resp = await client.get(
        "/api/v1/control/dead-letter?source_type=webhook",
        headers=_ceo_headers(),
    )
    assert resp.status_code == 200
    assert resp.json()["count"] == 1
    assert resp.json()["items"][0]["source_type"] == "webhook"


async def test_api_counts(client):
    await _seed_dead_letter(client, source_type="webhook", source_id="1")
    await _seed_dead_letter(client, source_type="scheduler", source_id="2")

    resp = await client.get("/api/v1/control/dead-letter/counts", headers=_ceo_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_pending"] == 2
    assert body["by_status"]["pending"] == 2
    assert body["by_source_type"]["webhook"] == 1
    assert body["by_source_type"]["scheduler"] == 1


async def test_api_get_single_entry(client):
    entry_id = await _seed_dead_letter(client, source_type="workflow", source_id="99")

    resp = await client.get(f"/api/v1/control/dead-letter/{entry_id}", headers=_ceo_headers())
    assert resp.status_code == 200
    assert resp.json()["id"] == entry_id
    assert resp.json()["source_type"] == "workflow"


async def test_api_get_nonexistent_returns_404(client):
    resp = await client.get("/api/v1/control/dead-letter/99999", headers=_ceo_headers())
    assert resp.status_code == 404


async def test_api_retry_entry(client):
    entry_id = await _seed_dead_letter(client, source_type="webhook", source_id="1")

    resp = await client.post(f"/api/v1/control/dead-letter/{entry_id}/retry", headers=_ceo_headers())
    assert resp.status_code == 200
    assert resp.json()["status"] == "retrying"
    assert resp.json()["attempts"] == 2


async def test_api_resolve_entry(client):
    entry_id = await _seed_dead_letter(client, source_type="scheduler", source_id="job1")

    resp = await client.post(f"/api/v1/control/dead-letter/{entry_id}/resolve", headers=_ceo_headers())
    assert resp.status_code == 200
    assert resp.json()["status"] == "resolved"


async def test_api_archive_entry(client):
    entry_id = await _seed_dead_letter(client, source_type="webhook", source_id="1")

    resp = await client.post(f"/api/v1/control/dead-letter/{entry_id}/archive", headers=_ceo_headers())
    assert resp.status_code == 200
    assert resp.json()["status"] == "archived"


# ── RBAC ──────────────────────────────────────────────────────────────────────

async def test_api_staff_denied_list(client):
    resp = await client.get("/api/v1/control/dead-letter", headers=_staff_headers())
    assert resp.status_code == 403


async def test_api_staff_denied_retry(client):
    resp = await client.post("/api/v1/control/dead-letter/1/retry", headers=_staff_headers())
    assert resp.status_code == 403


async def test_api_manager_can_view_counts(client):
    resp = await client.get("/api/v1/control/dead-letter/counts", headers=_manager_headers())
    assert resp.status_code == 200


async def test_api_manager_denied_list(client):
    resp = await client.get("/api/v1/control/dead-letter", headers=_manager_headers())
    assert resp.status_code == 403


# ── Signal topics exist ───────────────────────────────────────────────────────

def test_dead_letter_signal_topics_registered():
    from app.platform.signals.topics import (
        DEAD_LETTER_CAPTURED,
        DEAD_LETTER_RESOLVED,
        DEAD_LETTER_RETRIED,
    )
    assert DEAD_LETTER_CAPTURED == "dead_letter.captured"
    assert DEAD_LETTER_RETRIED == "dead_letter.retried"
    assert DEAD_LETTER_RESOLVED == "dead_letter.resolved"


# ── Feature flag ──────────────────────────────────────────────────────────────

def test_dead_letter_feature_flag_exists():
    from app.core.config import Settings
    assert "DEAD_LETTER_ENABLED" in Settings.model_fields
    assert "DEAD_LETTER_AUTO_ARCHIVE_DAYS" in Settings.model_fields


# ── Model structure ───────────────────────────────────────────────────────────

def test_dead_letter_model_has_required_columns():
    columns = {c.name for c in DeadLetterEntry.__table__.columns}
    required = {
        "id", "organization_id", "source_type", "source_id", "source_detail",
        "payload", "error_message", "error_type", "attempts", "max_attempts",
        "status", "resolved_by", "created_at", "resolved_at",
    }
    assert required.issubset(columns)
