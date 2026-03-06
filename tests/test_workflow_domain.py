import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models.signal import Signal


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
async def test_create_workflow_definition_emits_signal(db):
    from app.schemas.workflow_definition import WorkflowDefinitionCreate, WorkflowDefinitionStep
    from app.services import automation as automation_service

    row = await automation_service.create_workflow_definition(
        db,
        organization_id=1,
        workspace_id=None,
        actor_user_id=1,
        data=WorkflowDefinitionCreate(
            name="V2 Definition",
            steps=[WorkflowDefinitionStep(name="Fetch", action_type="fetch_calendar_digest")],
        ),
    )
    assert row.slug == "v2-definition"

    result = await db.execute(select(Signal).where(Signal.topic == "workflow.definition.created"))
    signal = result.scalar_one_or_none()
    assert signal is not None
    assert signal.organization_id == 1


@pytest.mark.asyncio
async def test_create_workflow_definition_rejects_invalid_params(db):
    from app.schemas.workflow_definition import WorkflowDefinitionCreate, WorkflowDefinitionStep
    from app.services import automation as automation_service

    with pytest.raises(ValueError, match="params must be an object"):
        await automation_service.create_workflow_definition(
            db,
            organization_id=1,
            workspace_id=None,
            actor_user_id=1,
            data=WorkflowDefinitionCreate(
                name="Invalid Definition",
                steps=[WorkflowDefinitionStep.model_construct(name="Bad", action_type="assign_task", params="bad")],
            ),
        )
