from __future__ import annotations

from app.domains.automation.models import WorkflowStepDecision
from app.engines.decision.workflow_policy import evaluate_workflow_step_policy
from app.platform.signals import SignalCategory, SignalEnvelope, publish_signal
from app.platform.signals.topics import WORKFLOW_PLAN_GENERATED, WORKFLOW_STEP_BLOCKED


async def build_workflow_execution_plan(
    db,
    *,
    organization_id: int,
    workspace_id: int | None,
    actor_user_id: int,
    run,
    definition,
) -> dict[str, object]:
    step_plans: list[dict[str, object]] = []
    for index, step in enumerate(definition.steps_json or []):
        decision, reason = evaluate_workflow_step_policy(step=step)
        step_plans.append(
            {
                "step_index": index,
                "step_key": str(step.get("key") or f"step-{index + 1}"),
                "action_type": str(step.get("action_type") or ""),
                "params": dict(step.get("params") or {}),
                "decision": decision.value,
                "reason": reason,
            }
        )
    payload = {
        "workflow_run_id": run.id,
        "workflow_definition_id": getattr(definition, "id", None),
        "workflow_version": getattr(definition, "version", None),
        "step_plans": step_plans,
    }
    await publish_signal(
        SignalEnvelope(
            topic=WORKFLOW_PLAN_GENERATED,
            category=SignalCategory.DECISION,
            organization_id=organization_id,
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            source="engines.decision.workflow_plans",
            entity_type="workflow_run",
            entity_id=str(run.id),
            payload=payload,
        ),
        db=db,
    )
    for sp in step_plans:
        if sp.get("decision") == WorkflowStepDecision.BLOCKED.value:
            await publish_signal(
                SignalEnvelope(
                    topic=WORKFLOW_STEP_BLOCKED,
                    category=SignalCategory.DECISION,
                    organization_id=organization_id,
                    workspace_id=workspace_id,
                    actor_user_id=actor_user_id,
                    source="engines.decision.workflow_plans",
                    entity_type="workflow_run",
                    entity_id=str(run.id),
                    payload={
                        "workflow_run_id": run.id,
                        "step_index": sp.get("step_index"),
                        "step_key": sp.get("step_key"),
                        "action_type": sp.get("action_type"),
                        "reason": sp.get("reason"),
                    },
                ),
                db=db,
            )
    return payload
