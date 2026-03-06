from __future__ import annotations


async def generate_workflow_plan_draft(
    *,
    actor: dict,
    organization_id: int,
    workspace_id: int | None,
    intent: str,
    constraints: dict,
    available_integrations: list[str],
) -> dict[str, object]:
    lowered = intent.strip().lower()
    wants_lead = "lead" in lowered or "crm" in lowered
    steps = [
        {
            "key": "collect-context",
            "name": "Collect context",
            "action_type": "fetch_calendar_digest" if "calendar" in lowered else "noop",
            "params": {},
            "requires_approval": False,
        }
    ]
    if wants_lead:
        steps.append(
            {
                "key": "assign-followup",
                "name": "Assign follow-up",
                "action_type": "assign_task",
                "params": {"task_id": 0},
                "requires_approval": True,
            }
        )
    else:
        steps.append(
            {
                "key": "notify-owner",
                "name": "Notify owner",
                "action_type": "unknown_noop",
                "params": {"message": intent[:200]},
                "requires_approval": False,
            }
        )
    return {
        "name": f"Workflow Draft for {actor['role'].title()}",
        "summary": f"Drafted workflow for org {organization_id} based on intent: {intent[:160]}",
        "trigger_mode": "manual",
        "steps": steps,
        "risk_level": "medium" if any(step["requires_approval"] for step in steps) else "low",
        "confidence": 0.72,
        "workspace_id": workspace_id,
        "constraints": constraints,
        "available_integrations": available_integrations,
    }
