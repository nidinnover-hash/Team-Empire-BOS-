"""Tests for automation triggers and multi-step workflows."""

import pytest

# ── Trigger CRUD ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_trigger(client):
    r = await client.post("/api/v1/automations/triggers", json={
        "name": "Notify on task create",
        "source_event": "task.created",
        "action_type": "send_slack_message",
        "action_integration": "slack",
        "action_params": {"channel": "#general", "text": "New task created"},
    })
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "Notify on task create"
    assert data["source_event"] == "task.created"
    assert data["action_type"] == "send_slack_message"
    assert data["is_active"] is True
    assert data["fire_count"] == 0


@pytest.mark.asyncio
async def test_list_triggers(client):
    await client.post("/api/v1/automations/triggers", json={
        "name": "T1", "source_event": "task.created", "action_type": "noop",
    })
    await client.post("/api/v1/automations/triggers", json={
        "name": "T2", "source_event": "approval.approved", "action_type": "noop",
    })
    r = await client.get("/api/v1/automations/triggers")
    assert r.status_code == 200
    assert len(r.json()) >= 2


@pytest.mark.asyncio
async def test_get_trigger(client):
    r1 = await client.post("/api/v1/automations/triggers", json={
        "name": "Get me", "source_event": "e1", "action_type": "a1",
    })
    tid = r1.json()["id"]
    r2 = await client.get(f"/api/v1/automations/triggers/{tid}")
    assert r2.status_code == 200
    assert r2.json()["name"] == "Get me"


@pytest.mark.asyncio
async def test_update_trigger(client):
    r1 = await client.post("/api/v1/automations/triggers", json={
        "name": "Original", "source_event": "e1", "action_type": "a1",
    })
    tid = r1.json()["id"]
    r2 = await client.patch(f"/api/v1/automations/triggers/{tid}", json={
        "name": "Updated", "is_active": False,
    })
    assert r2.status_code == 200
    assert r2.json()["name"] == "Updated"
    assert r2.json()["is_active"] is False


@pytest.mark.asyncio
async def test_delete_trigger(client):
    r1 = await client.post("/api/v1/automations/triggers", json={
        "name": "Delete me", "source_event": "e1", "action_type": "a1",
    })
    tid = r1.json()["id"]
    r2 = await client.delete(f"/api/v1/automations/triggers/{tid}")
    assert r2.status_code == 204
    r3 = await client.get(f"/api/v1/automations/triggers/{tid}")
    assert r3.status_code == 404


@pytest.mark.asyncio
async def test_trigger_not_found(client):
    r = await client.get("/api/v1/automations/triggers/99999")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_create_trigger_with_filter(client):
    r = await client.post("/api/v1/automations/triggers", json={
        "name": "Filtered",
        "source_event": "task.created",
        "action_type": "notify",
        "filter_json": {"priority": 4},
        "requires_approval": True,
    })
    assert r.status_code == 201
    data = r.json()
    assert data["filter_json"] == {"priority": 4}
    assert data["requires_approval"] is True


# ── Trigger active_only filter ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_triggers_active_only(client):
    await client.post("/api/v1/automations/triggers", json={
        "name": "Active", "source_event": "e1", "action_type": "a1",
    })
    r2 = await client.post("/api/v1/automations/triggers", json={
        "name": "Inactive", "source_event": "e2", "action_type": "a2",
    })
    tid = r2.json()["id"]
    await client.patch(f"/api/v1/automations/triggers/{tid}", json={"is_active": False})

    r = await client.get("/api/v1/automations/triggers?active_only=true")
    assert r.status_code == 200
    names = [t["name"] for t in r.json()]
    assert "Active" in names
    assert "Inactive" not in names


# ── Workflow CRUD ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_workflow(client):
    r = await client.post("/api/v1/automations/workflows", json={
        "name": "Onboard flow",
        "description": "New hire onboarding",
        "steps": [
            {"name": "Create ClickUp task", "action_type": "clickup.create_task", "params": {"list_id": "123"}},
            {"name": "Send welcome email", "action_type": "email.send", "params": {"template": "welcome"}},
            {"name": "Notify Slack", "action_type": "slack.post_message", "integration": "slack", "params": {"channel": "#team"}},
        ],
    })
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "Onboard flow"
    assert data["status"] == "draft"
    assert len(data["steps_json"]) == 3
    assert data["current_step"] == 0


@pytest.mark.asyncio
async def test_list_workflows(client):
    await client.post("/api/v1/automations/workflows", json={
        "name": "W1", "steps": [{"name": "s1", "action_type": "a1"}],
    })
    r = await client.get("/api/v1/automations/workflows")
    assert r.status_code == 200
    assert len(r.json()) >= 1


@pytest.mark.asyncio
async def test_start_workflow(client):
    r1 = await client.post("/api/v1/automations/workflows", json={
        "name": "Start me", "steps": [{"name": "s1", "action_type": "a1"}],
    })
    wid = r1.json()["id"]
    r2 = await client.post(f"/api/v1/automations/workflows/{wid}/start")
    assert r2.status_code == 200
    assert r2.json()["status"] == "running"
    assert r2.json()["started_at"] is not None


@pytest.mark.asyncio
async def test_advance_workflow(client):
    r1 = await client.post("/api/v1/automations/workflows", json={
        "name": "Advance me",
        "steps": [
            {"name": "step1", "action_type": "a1"},
            {"name": "step2", "action_type": "a2"},
        ],
    })
    wid = r1.json()["id"]
    await client.post(f"/api/v1/automations/workflows/{wid}/start")

    r2 = await client.post(f"/api/v1/automations/workflows/{wid}/advance", json={"output": "ok"})
    assert r2.status_code == 200
    assert r2.json()["current_step"] == 1
    assert r2.json()["status"] == "running"

    r3 = await client.post(f"/api/v1/automations/workflows/{wid}/advance")
    assert r3.status_code == 200
    assert r3.json()["status"] == "completed"
    assert r3.json()["finished_at"] is not None


@pytest.mark.asyncio
async def test_workflow_not_found(client):
    r = await client.get("/api/v1/automations/workflows/99999")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_start_already_running_workflow_fails(client):
    r1 = await client.post("/api/v1/automations/workflows", json={
        "name": "Already running", "steps": [{"name": "s1", "action_type": "a1"}],
    })
    wid = r1.json()["id"]
    await client.post(f"/api/v1/automations/workflows/{wid}/start")
    r2 = await client.post(f"/api/v1/automations/workflows/{wid}/start")
    assert r2.status_code == 409


# ── Trigger service fire_matching_triggers ───────────────────────────────────


@pytest.mark.asyncio
async def test_fire_matching_triggers(db):
    from app.services.automation import create_trigger, fire_matching_triggers

    await create_trigger(
        db, organization_id=1,
        name="Match me", source_event="task.created", action_type="noop",
    )
    await create_trigger(
        db, organization_id=1,
        name="No match", source_event="approval.approved", action_type="noop",
    )
    matched = await fire_matching_triggers(db, organization_id=1, event_type="task.created")
    assert len(matched) == 1
    assert matched[0].name == "Match me"
    assert matched[0].fire_count == 1


@pytest.mark.asyncio
async def test_fire_triggers_with_filter_match(db):
    from app.services.automation import create_trigger, fire_matching_triggers

    await create_trigger(
        db, organization_id=1,
        name="Filtered", source_event="task.created", action_type="noop",
        filter_json={"priority": 4},
    )
    matched = await fire_matching_triggers(
        db, organization_id=1, event_type="task.created",
        event_payload={"priority": 4, "title": "Urgent"},
    )
    assert len(matched) == 1

    no_match = await fire_matching_triggers(
        db, organization_id=1, event_type="task.created",
        event_payload={"priority": 1},
    )
    assert len(no_match) == 0


# ── Workflow service ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_workflow_lifecycle(db):
    from app.services.automation import (
        advance_workflow,
        create_workflow,
        fail_workflow,
        start_workflow,
    )

    wf = await create_workflow(
        db, organization_id=1,
        name="Test WF",
        steps_json=[{"name": "s1", "action_type": "a1"}, {"name": "s2", "action_type": "a2"}],
    )
    assert wf.status == "draft"

    wf = await start_workflow(db, wf.id, organization_id=1)
    assert wf is not None
    assert wf.status == "running"

    wf = await advance_workflow(db, wf.id, organization_id=1, step_result={"ok": True})
    assert wf is not None
    assert wf.current_step == 1

    wf = await fail_workflow(db, wf.id, organization_id=1, error_text="step 2 failed")
    assert wf is not None
    assert wf.status == "failed"
    assert wf.error_text == "step 2 failed"


@pytest.mark.asyncio
async def test_create_workflow_rejects_invalid_step_params_service(db):
    from app.services.automation import create_workflow

    with pytest.raises(ValueError, match="params must be an object"):
        await create_workflow(
            db,
            organization_id=1,
            name="Invalid Params",
            steps_json=[
                {"name": "bad", "action_type": "assign_task", "params": "not-a-dict"},
            ],
        )


@pytest.mark.asyncio
async def test_create_workflow_normalizes_action_type_service(db):
    from app.services.automation import create_workflow

    wf = await create_workflow(
        db,
        organization_id=1,
        name="Normalize Action Type",
        steps_json=[
            {"name": "step1", "action_type": "Assign_Task", "params": {"task_id": 1}},
        ],
    )
    assert wf.steps_json[0]["action_type"] == "assign_task"
