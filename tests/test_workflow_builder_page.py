import pytest

from app.core.config import settings


@pytest.fixture(autouse=True)
def _workflow_flags():
    saved = (
        settings.FEATURE_WORKFLOW_V2,
        settings.FEATURE_WORKFLOW_RUNS,
        settings.FEATURE_WORKFLOW_BUILDER_SSR,
        settings.FEATURE_WORKFLOW_OBSERVABILITY,
        settings.FEATURE_WORKFLOW_COPILOT,
    )
    object.__setattr__(settings, "FEATURE_WORKFLOW_V2", True)
    object.__setattr__(settings, "FEATURE_WORKFLOW_RUNS", True)
    object.__setattr__(settings, "FEATURE_WORKFLOW_BUILDER_SSR", True)
    object.__setattr__(settings, "FEATURE_WORKFLOW_OBSERVABILITY", True)
    object.__setattr__(settings, "FEATURE_WORKFLOW_COPILOT", True)
    yield
    object.__setattr__(settings, "FEATURE_WORKFLOW_V2", saved[0])
    object.__setattr__(settings, "FEATURE_WORKFLOW_RUNS", saved[1])
    object.__setattr__(settings, "FEATURE_WORKFLOW_BUILDER_SSR", saved[2])
    object.__setattr__(settings, "FEATURE_WORKFLOW_OBSERVABILITY", saved[3])
    object.__setattr__(settings, "FEATURE_WORKFLOW_COPILOT", saved[4])


@pytest.mark.asyncio
async def test_automations_page_contains_workflow_studio(client):
    response = await client.get("/web/automations", follow_redirects=False)
    assert response.status_code in (200, 302)
    if response.status_code == 302:
        assert response.headers["location"] == "/web/login"
        return
    text = response.text
    assert "Workflow Studio" in text
    assert "Workflow Builder" in text
    assert "Workflow Copilot" in text
