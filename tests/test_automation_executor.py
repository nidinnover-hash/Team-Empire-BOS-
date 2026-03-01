"""Tests for the workflow step executor and audit-driven trigger firing."""

import pytest

# ── Workflow step executor ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_workflow_executes_all_steps(db):
    from app.services.automation import create_workflow, run_workflow

    wf = await create_workflow(
        db, organization_id=1,
        name="Exec test",
        steps_json=[
            {"name": "s1", "action_type": "assign_task", "params": {"task_id": 42}},
            {"name": "s2", "action_type": "unknown_noop", "params": {}},
        ],
    )
    wf = await run_workflow(db, wf.id, organization_id=1)
    assert wf is not None
    assert wf.status == "completed"
    assert wf.current_step == 2
    # Step 0 used assign_task handler, step 1 was skipped (no handler)
    assert wf.result_json["step_0"]["status"] == "succeeded"
    assert wf.result_json["step_1"]["status"] == "skipped"


@pytest.mark.asyncio
async def test_execute_current_step_skips_unknown_action(db):
    from app.services.automation import (
        create_workflow,
        execute_current_step,
        start_workflow,
    )

    wf = await create_workflow(
        db, organization_id=1,
        name="Skip test",
        steps_json=[{"name": "s1", "action_type": "nonexistent_handler"}],
    )
    wf = await start_workflow(db, wf.id, organization_id=1)
    assert wf is not None
    wf = await execute_current_step(db, wf.id, organization_id=1)
    assert wf is not None
    assert wf.status == "completed"
    assert wf.result_json["step_0"]["status"] == "skipped"


@pytest.mark.asyncio
async def test_execute_current_step_fails_on_handler_error(db):
    from app.services.automation import (
        create_workflow,
        execute_current_step,
        start_workflow,
    )

    wf = await create_workflow(
        db, organization_id=1,
        name="Fail test",
        steps_json=[
            {"name": "s1", "action_type": "spend", "params": {"amount": -1}},
        ],
    )
    wf = await start_workflow(db, wf.id, organization_id=1)
    assert wf is not None
    wf = await execute_current_step(db, wf.id, organization_id=1)
    assert wf is not None
    assert wf.status == "failed"
    assert "Amount must be greater than zero" in (wf.error_text or "")


@pytest.mark.asyncio
async def test_run_workflow_via_api(client):
    r1 = await client.post("/api/v1/automations/workflows", json={
        "name": "API run test",
        "steps": [
            {"name": "s1", "action_type": "assign_task", "params": {"task_id": 1}},
        ],
    })
    assert r1.status_code == 201
    wid = r1.json()["id"]

    r2 = await client.post(f"/api/v1/automations/workflows/{wid}/run")
    assert r2.status_code == 200
    data = r2.json()
    assert data["status"] == "completed"
    assert data["current_step"] == 1


# ── Audit-driven trigger firing ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_record_action_fires_matching_trigger(db):
    from app.logs.audit import record_action
    from app.services.automation import create_trigger, get_trigger

    trigger = await create_trigger(
        db, organization_id=1,
        name="On task create",
        source_event="task_created",
        action_type="notify",
    )
    assert trigger.fire_count == 0

    # record_action should fire the matching trigger
    await record_action(
        db,
        event_type="task_created",
        actor_user_id=1,
        organization_id=1,
        entity_type="task",
        entity_id=99,
        payload_json={"title": "New task"},
    )

    updated = await get_trigger(db, trigger.id, organization_id=1)
    assert updated is not None
    assert updated.fire_count == 1


@pytest.mark.asyncio
async def test_record_action_does_not_fire_unrelated_trigger(db):
    from app.logs.audit import record_action
    from app.services.automation import create_trigger, get_trigger

    trigger = await create_trigger(
        db, organization_id=1,
        name="On approval",
        source_event="approval_approved",
        action_type="notify",
    )

    await record_action(
        db,
        event_type="task_created",
        actor_user_id=1,
        organization_id=1,
    )

    updated = await get_trigger(db, trigger.id, organization_id=1)
    assert updated is not None
    assert updated.fire_count == 0


@pytest.mark.asyncio
async def test_automations_page_loads(client):
    r = await client.get("/web/automations", follow_redirects=False)
    # Should redirect to login (no session cookie in test client) or return 200
    assert r.status_code in (200, 302)
