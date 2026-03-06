import pytest

from app.core.config import settings


@pytest.fixture(autouse=True)
def _workflow_flags():
    saved = (
        settings.FEATURE_WORKFLOW_COPILOT,
        settings.FEATURE_WORKFLOW_V2,
    )
    object.__setattr__(settings, "FEATURE_WORKFLOW_COPILOT", True)
    object.__setattr__(settings, "FEATURE_WORKFLOW_V2", True)
    yield
    object.__setattr__(settings, "FEATURE_WORKFLOW_COPILOT", saved[0])
    object.__setattr__(settings, "FEATURE_WORKFLOW_V2", saved[1])


@pytest.mark.asyncio
async def test_workflow_copilot_plan_returns_draft_only(client):
    response = await client.post(
        "/api/v1/automations/copilot/plan",
        json={
            "intent": "Build a workflow to triage inbound leads and assign follow-up after approval",
            "constraints": {"approval_required": True},
            "available_integrations": ["hubspot", "slack"],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["steps"]
    assert any(step["requires_approval"] for step in payload["steps"])
