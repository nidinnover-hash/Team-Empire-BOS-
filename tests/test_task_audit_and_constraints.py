"""Tests for task audit logging and model constraint enforcement."""
from __future__ import annotations


# ── Task CRUD creates audit events ──────────────────────────────────────────


async def test_create_task_generates_audit_event(client):
    """POST /tasks should log task_created audit event."""
    # Create task
    resp = await client.post("/api/v1/tasks", json={"title": "Auditable task"})
    assert resp.status_code == 201

    # Verify audit trail contains the creation event
    audit_resp = await client.get("/api/v1/ops/events?limit=5")
    assert audit_resp.status_code == 200
    events = audit_resp.json()
    created_events = [e for e in events if e.get("event_type") == "task_created"]
    assert len(created_events) >= 1
    assert created_events[0]["entity_type"] == "task"


async def test_update_task_generates_audit_event(client):
    """PATCH /tasks/{id} should log task_updated audit event."""
    task_id = (await client.post("/api/v1/tasks", json={"title": "To update"})).json()["id"]
    await client.patch(f"/api/v1/tasks/{task_id}", json={"priority": 4})

    audit_resp = await client.get("/api/v1/ops/events?limit=5")
    assert audit_resp.status_code == 200
    events = audit_resp.json()
    updated_events = [e for e in events if e.get("event_type") == "task_updated"]
    assert len(updated_events) >= 1


async def test_delete_task_generates_audit_event(client):
    """DELETE /tasks/{id} should log task_deleted audit event."""
    task_id = (await client.post("/api/v1/tasks", json={"title": "To delete"})).json()["id"]
    resp = await client.delete(f"/api/v1/tasks/{task_id}")
    assert resp.status_code == 204

    audit_resp = await client.get("/api/v1/ops/events?limit=5")
    assert audit_resp.status_code == 200
    events = audit_resp.json()
    deleted_events = [e for e in events if e.get("event_type") == "task_deleted"]
    assert len(deleted_events) >= 1


# ── Task model constraint: completed_at required when is_done ────────────────


async def test_mark_done_always_sets_completed_at(client):
    """When marking a task done, completed_at must be non-null."""
    task_id = (await client.post("/api/v1/tasks", json={"title": "Check constraint"})).json()["id"]
    resp = await client.patch(f"/api/v1/tasks/{task_id}", json={"is_done": True})
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_done"] is True
    assert body["completed_at"] is not None


async def test_reopen_task_clears_completed_at(client):
    """Reopening a task must clear completed_at to satisfy the CHECK constraint."""
    task_id = (await client.post("/api/v1/tasks", json={"title": "Constraint check"})).json()["id"]
    await client.patch(f"/api/v1/tasks/{task_id}", json={"is_done": True})
    resp = await client.patch(f"/api/v1/tasks/{task_id}", json={"is_done": False})
    body = resp.json()
    assert body["is_done"] is False
    assert body["completed_at"] is None
