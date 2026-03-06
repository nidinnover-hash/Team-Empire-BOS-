import pytest

from app.core.config import settings


@pytest.fixture(autouse=True)
def _workflow_flags():
    saved = (
        settings.FEATURE_WORKFLOW_V2,
        settings.FEATURE_WORKFLOW_RUNS,
        settings.FEATURE_WORKFLOW_APPROVAL_PIPELINE,
        settings.FEATURE_WORKFLOW_OBSERVABILITY,
    )
    object.__setattr__(settings, "FEATURE_WORKFLOW_V2", True)
    object.__setattr__(settings, "FEATURE_WORKFLOW_RUNS", True)
    object.__setattr__(settings, "FEATURE_WORKFLOW_APPROVAL_PIPELINE", True)
    object.__setattr__(settings, "FEATURE_WORKFLOW_OBSERVABILITY", True)
    yield
    object.__setattr__(settings, "FEATURE_WORKFLOW_V2", saved[0])
    object.__setattr__(settings, "FEATURE_WORKFLOW_RUNS", saved[1])
    object.__setattr__(settings, "FEATURE_WORKFLOW_APPROVAL_PIPELINE", saved[2])
    object.__setattr__(settings, "FEATURE_WORKFLOW_OBSERVABILITY", saved[3])


@pytest.mark.asyncio
async def test_workflow_observability_summary_and_runs(client):
    create = await client.post(
        "/api/v1/automations/workflow-definitions",
        json={
            "name": "Observe Definition",
            "steps": [{"name": "Fetch", "action_type": "fetch_calendar_digest", "params": {}}],
        },
    )
    definition_id = create.json()["id"]
    await client.post(f"/api/v1/automations/workflow-definitions/{definition_id}/publish")
    run = await client.post(
        f"/api/v1/automations/workflow-definitions/{definition_id}/run",
        json={"trigger_source": "manual"},
    )
    assert run.status_code == 200

    summary = await client.get("/api/v1/workflow-observability/summary")
    assert summary.status_code == 200
    assert summary.json()["total_runs"] >= 1

    runs = await client.get("/api/v1/workflow-observability/runs")
    assert runs.status_code == 200
    assert len(runs.json()) >= 1

    detail = await client.get(f"/api/v1/workflow-observability/runs/{run.json()['id']}")
    assert detail.status_code == 200
    assert detail.json()["id"] == run.json()["id"]
