"""Tests for bulk CSV import and batch operations."""
from __future__ import annotations

import io

import pytest


def _csv_file(content: str, filename: str = "test.csv"):
    """Create an upload-compatible file tuple for httpx."""
    return {"file": (filename, io.BytesIO(content.encode("utf-8")), "text/csv")}


# ── CSV import contacts ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_import_contacts_csv(client):
    """Import valid CSV creates contacts."""
    csv = "name,email,phone,company,relationship,pipeline_stage\nAlice,alice@csv.com,+111,ACME,business,new\nBob,bob@csv.com,,Corp,personal,contacted\n"
    resp = await client.post("/api/v1/bulk/import/contacts", files=_csv_file(csv))
    assert resp.status_code == 200
    data = resp.json()
    assert data["imported"] == 2
    assert data["skipped"] == 0


@pytest.mark.asyncio
async def test_import_contacts_csv_skips_missing_name(client):
    """Rows without name are skipped."""
    csv = "name,email\n,no-name@test.com\nValid,valid@test.com\n"
    resp = await client.post("/api/v1/bulk/import/contacts", files=_csv_file(csv))
    data = resp.json()
    assert data["imported"] == 1
    assert data["skipped"] == 1
    assert any("missing" in e.lower() for e in data["errors"])


@pytest.mark.asyncio
async def test_import_contacts_csv_deduplicates_by_email(client):
    """Duplicate emails are skipped."""
    # First import
    csv1 = "name,email\nFirst,dup@test.com\n"
    await client.post("/api/v1/bulk/import/contacts", files=_csv_file(csv1))

    # Second import with same email
    csv2 = "name,email\nSecond,dup@test.com\n"
    resp = await client.post("/api/v1/bulk/import/contacts", files=_csv_file(csv2))
    data = resp.json()
    assert data["skipped"] == 1
    assert data["imported"] == 0


@pytest.mark.asyncio
async def test_import_contacts_csv_normalizes_relationship(client):
    """Invalid relationship values default to 'personal'."""
    csv = "name,relationship\nTest,invalid_type\n"
    resp = await client.post("/api/v1/bulk/import/contacts", files=_csv_file(csv))
    assert resp.json()["imported"] == 1


# ── CSV import tasks ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_import_tasks_csv(client):
    """Import valid CSV creates tasks."""
    csv = "title,description,priority,category\nTask A,Do stuff,1,business\nTask B,More stuff,3,personal\n"
    resp = await client.post("/api/v1/bulk/import/tasks", files=_csv_file(csv))
    assert resp.status_code == 200
    data = resp.json()
    assert data["imported"] == 2
    assert data["skipped"] == 0


@pytest.mark.asyncio
async def test_import_tasks_csv_skips_missing_title(client):
    """Rows without title are skipped."""
    csv = "title,category\n,business\nValid Task,business\n"
    resp = await client.post("/api/v1/bulk/import/tasks", files=_csv_file(csv))
    data = resp.json()
    assert data["imported"] == 1
    assert data["skipped"] == 1


@pytest.mark.asyncio
async def test_import_tasks_csv_normalizes_priority(client):
    """Invalid priority defaults to 2, out-of-range clamped."""
    csv = "title,priority\nHighP,1\nBadP,abc\nOverP,99\n"
    resp = await client.post("/api/v1/bulk/import/tasks", files=_csv_file(csv))
    assert resp.json()["imported"] == 3


# ── Batch operations ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_batch_delete_contacts(client):
    """Batch delete removes contacts."""
    ids = []
    for i in range(3):
        r = await client.post("/api/v1/contacts", json={
            "name": f"BatchDel {i}", "relationship": "business",
        })
        ids.append(r.json()["id"])

    resp = await client.post("/api/v1/bulk/contacts/delete", json={"ids": ids})
    assert resp.status_code == 200
    data = resp.json()
    assert data["deleted"] == 3
    assert data["not_found"] == 0


@pytest.mark.asyncio
async def test_batch_delete_nonexistent(client):
    """Batch delete with nonexistent IDs returns not_found count."""
    resp = await client.post("/api/v1/bulk/contacts/delete", json={"ids": [99998, 99999]})
    assert resp.status_code == 200
    assert resp.json()["not_found"] == 2
    assert resp.json()["deleted"] == 0


@pytest.mark.asyncio
async def test_batch_update_stage(client):
    """Batch update moves contacts to specified pipeline stage."""
    ids = []
    for i in range(2):
        r = await client.post("/api/v1/contacts", json={
            "name": f"StageUpd {i}", "pipeline_stage": "new", "relationship": "business",
        })
        ids.append(r.json()["id"])

    resp = await client.post("/api/v1/bulk/contacts/update-stage", json={
        "ids": ids, "pipeline_stage": "qualified",
    })
    assert resp.status_code == 200
    assert resp.json()["updated"] == 2

    # Verify stage changed
    for cid in ids:
        c = await client.get(f"/api/v1/contacts/{cid}")
        assert c.json()["pipeline_stage"] == "qualified"


@pytest.mark.asyncio
async def test_batch_update_invalid_stage(client):
    """Batch update with invalid stage returns error."""
    r = await client.post("/api/v1/contacts", json={
        "name": "BadStage", "relationship": "business",
    })
    resp = await client.post("/api/v1/bulk/contacts/update-stage", json={
        "ids": [r.json()["id"]], "pipeline_stage": "invalid_stage",
    })
    assert resp.status_code == 200
    assert "error" in resp.json()
