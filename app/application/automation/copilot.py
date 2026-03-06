from __future__ import annotations

from app.engines.brain.workflow_planner import generate_workflow_plan_draft


async def build_workflow_copilot_plan(
    *,
    actor: dict,
    organization_id: int,
    workspace_id: int | None,
    intent: str,
    constraints: dict,
    available_integrations: list[str],
) -> dict[str, object]:
    return await generate_workflow_plan_draft(
        actor=actor,
        organization_id=organization_id,
        workspace_id=workspace_id,
        intent=intent,
        constraints=constraints,
        available_integrations=available_integrations,
    )
