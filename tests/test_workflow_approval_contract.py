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
async def test_workflow_reject_marks_run_failed(client):
    create = await client.post(
        "/api/v1/automations/workflow-definitions",
        json={
            "name": "Reject Definition",
            "steps": [{"name": "Assign", "action_type": "assign_task", "params": {"task_id": 2}}],
        },
    )
    definition_id = create.json()["id"]
    await client.post(f"/api/v1/automations/workflow-definitions/{definition_id}/publish")
    run = await client.post(
        f"/api/v1/automations/workflow-definitions/{definition_id}/run",
        json={"trigger_source": "manual"},
    )
    approval_id = run.json()["approval_id"]
    reject = await client.post(f"/api/v1/approvals/{approval_id}/reject", json={"note": "no"})
    assert reject.status_code == 200
    detail = await client.get(f"/api/v1/automations/workflow-runs/{run.json()['id']}")
    assert detail.status_code == 200
    assert detail.json()["status"] == "failed"
