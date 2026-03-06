import pytest

from app.core.config import settings


@pytest.fixture(autouse=True)
def _workflow_flags():
    saved = (
        settings.FEATURE_WORKFLOW_V2,
        settings.FEATURE_WORKFLOW_RUNS,
        settings.FEATURE_WORKFLOW_APPROVAL_PIPELINE,
    )
    object.__setattr__(settings, "FEATURE_WORKFLOW_V2", True)
    object.__setattr__(settings, "FEATURE_WORKFLOW_RUNS", True)
    object.__setattr__(settings, "FEATURE_WORKFLOW_APPROVAL_PIPELINE", True)
    yield
    object.__setattr__(settings, "FEATURE_WORKFLOW_V2", saved[0])
    object.__setattr__(settings, "FEATURE_WORKFLOW_RUNS", saved[1])
    object.__setattr__(settings, "FEATURE_WORKFLOW_APPROVAL_PIPELINE", saved[2])


@pytest.mark.asyncio
async def test_workflow_definition_run_waits_for_approval(client):
    create = await client.post(
        "/api/v1/automations/workflow-definitions",
        json={
            "name": "Approve Me",
            "steps": [{"name": "Assign", "action_type": "assign_task", "params": {"task_id": 7}}],
        },
    )
    assert create.status_code == 201
    definition_id = create.json()["id"]

    publish = await client.post(f"/api/v1/automations/workflow-definitions/{definition_id}/publish")
    assert publish.status_code == 200

    run = await client.post(
        f"/api/v1/automations/workflow-definitions/{definition_id}/run",
        json={"trigger_source": "manual", "input_json": {"ticket": "A-1"}},
    )
    assert run.status_code == 200
    payload = run.json()
    assert payload["status"] == "awaiting_approval"
    assert payload["approval_id"] is not None
    assert payload["step_runs"][0]["status"] == "awaiting_approval"

    approve = await client.post(f"/api/v1/approvals/{payload['approval_id']}/approve", json={"note": "approved"})
    assert approve.status_code == 200

    run_detail = await client.get(f"/api/v1/automations/workflow-runs/{payload['id']}")
    assert run_detail.status_code == 200
    run_payload = run_detail.json()
    assert run_payload["status"] == "completed"
    assert run_payload["step_runs"][0]["execution_id"] is not None


@pytest.mark.asyncio
async def test_workflow_definition_run_preview_shows_step_decisions(client):
    create = await client.post(
        "/api/v1/automations/workflow-definitions",
        json={
            "name": "Preview Definition",
            "steps": [
                {"name": "Fetch", "action_type": "fetch_calendar_digest", "params": {}},
                {"name": "Spend", "action_type": "spend", "params": {"amount": 5}},
            ],
        },
    )
    definition_id = create.json()["id"]
    preview = await client.post(
        f"/api/v1/automations/workflow-definitions/{definition_id}/run-preview",
        json={"input_json": {}},
    )
    assert preview.status_code == 200
    payload = preview.json()
    assert payload["requires_publish"] is True
    assert payload["step_plans"][0]["decision"] == "safe_auto"
    assert payload["step_plans"][1]["decision"] == "requires_approval"
