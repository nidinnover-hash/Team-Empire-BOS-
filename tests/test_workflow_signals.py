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
async def test_workflow_run_emits_run_and_step_signals(db):
    from app.schemas.workflow_definition import WorkflowDefinitionCreate, WorkflowDefinitionStep
    from app.services import automation as automation_service

    definition = await automation_service.create_workflow_definition(
        db,
        organization_id=1,
        workspace_id=None,
        actor_user_id=1,
        data=WorkflowDefinitionCreate(
            name="Signal Definition",
            steps=[WorkflowDefinitionStep(name="Fetch", action_type="fetch_calendar_digest")],
        ),
    )
    await automation_service.publish_workflow_definition(
        db,
        organization_id=1,
        workflow_definition_id=definition.id,
        actor_user_id=1,
    )
    run = await automation_service.run_workflow_definition(
        db,
        organization_id=1,
        workspace_id=None,
        actor_user_id=1,
        workflow_definition_id=definition.id,
        trigger_source="manual",
    )
    assert run is not None

    rows = (
        await db.execute(
            select(Signal.topic).where(
                Signal.organization_id == 1,
                Signal.topic.in_(
                    [
                        "workflow.run.created",
                        "workflow.run.started",
                        "workflow.run.completed",
                        "workflow.step.started",
                        "workflow.step.completed",
                    ]
                ),
            )
        )
    ).scalars().all()
    assert "workflow.run.created" in rows
    assert "workflow.step.completed" in rows
