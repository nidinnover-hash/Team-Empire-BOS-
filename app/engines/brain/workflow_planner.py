from __future__ import annotations

import json
import logging

from app.core.config import settings
from app.engines.brain.workflow_prompts import WORKFLOW_COPILOT_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

KNOWN_ACTION_TYPES = [
    "send_email",
    "send_slack",
    "create_task",
    "assign_task",
    "fetch_calendar_digest",
    "ai_generate",
    "http_request",
    "wait",
    "change_crm_status",
    "assign_leads",
    "noop",
]


async def generate_workflow_plan_draft(
    *,
    actor: dict,
    organization_id: int,
    workspace_id: int | None,
    intent: str,
    constraints: dict,
    available_integrations: list[str],
) -> dict[str, object]:
    """Use AI to generate a structured workflow plan from natural language intent.

    Falls back to a keyword-based heuristic if AI call fails.
    """
    try:
        return await _ai_generate_plan(
            actor=actor,
            organization_id=organization_id,
            workspace_id=workspace_id,
            intent=intent,
            constraints=constraints,
            available_integrations=available_integrations,
        )
    except Exception:
        logger.warning("AI workflow plan generation failed, using heuristic", exc_info=True)
        return _heuristic_plan(
            actor=actor,
            organization_id=organization_id,
            workspace_id=workspace_id,
            intent=intent,
            constraints=constraints,
            available_integrations=available_integrations,
        )


async def _ai_generate_plan(
    *,
    actor: dict,
    organization_id: int,
    workspace_id: int | None,
    intent: str,
    constraints: dict,
    available_integrations: list[str],
) -> dict[str, object]:
    from app.engines.brain.router import call_ai

    user_prompt = (
        f"Intent: {intent}\n"
        f"Available integrations: {', '.join(available_integrations) or 'none'}\n"
        f"Actor role: {actor.get('role', 'unknown')}\n"
        f"Constraints: {json.dumps(constraints) if constraints else 'none'}\n\n"
        f"Known action types: {', '.join(KNOWN_ACTION_TYPES)}\n\n"
        "Generate a workflow plan as JSON with this exact structure:\n"
        "{\n"
        '  "name": "short workflow name",\n'
        '  "summary": "one-line description",\n'
        '  "trigger_mode": "manual",\n'
        '  "risk_level": "low|medium|high",\n'
        '  "steps": [\n'
        "    {\n"
        '      "key": "step-slug",\n'
        '      "name": "Human-readable step name",\n'
        '      "action_type": "one of the known action types",\n'
        '      "params": {},\n'
        '      "requires_approval": true/false\n'
        "    }\n"
        "  ]\n"
        "}\n\n"
        "Rules:\n"
        "- Use only action types from the known list above\n"
        "- Mark mutating actions (send_email, send_slack, change_crm_status) as requires_approval=true\n"
        "- Read-only actions (fetch_calendar_digest, ai_generate) are requires_approval=false\n"
        "- Keep it practical: 2-6 steps\n"
        "- Return ONLY valid JSON, no markdown fences"
    )

    raw = await call_ai(
        system_prompt=WORKFLOW_COPILOT_SYSTEM_PROMPT,
        user_message=user_prompt,
        provider="openai",
        max_tokens=1000,
        organization_id=organization_id,
    )

    plan = _parse_ai_response(raw)
    plan["workspace_id"] = workspace_id
    plan["constraints"] = constraints
    plan["available_integrations"] = available_integrations
    plan["confidence"] = 0.85
    plan.setdefault("trigger_mode", "manual")
    plan.setdefault("risk_level", _infer_risk_level(plan.get("steps", [])))
    return plan


def _parse_ai_response(raw: str) -> dict:
    """Extract JSON from AI response, stripping markdown fences if present."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)
    plan = json.loads(text)
    if not isinstance(plan, dict) or "steps" not in plan:
        raise ValueError("AI response missing 'steps' key")
    for step in plan["steps"]:
        if step.get("action_type") not in KNOWN_ACTION_TYPES:
            step["action_type"] = "noop"
            step["requires_approval"] = False
    return plan


def _infer_risk_level(steps: list[dict]) -> str:
    if any(s.get("requires_approval") for s in steps):
        return "medium"
    return "low"


def _heuristic_plan(
    *,
    actor: dict,
    organization_id: int,
    workspace_id: int | None,
    intent: str,
    constraints: dict,
    available_integrations: list[str],
) -> dict[str, object]:
    """Keyword-based fallback when AI is unavailable."""
    lowered = intent.strip().lower()
    steps: list[dict] = []

    if "email" in lowered or "mail" in lowered:
        steps.append({
            "key": "draft-email",
            "name": "Draft email with AI",
            "action_type": "ai_generate",
            "params": {"prompt": f"Draft an email: {intent[:200]}"},
            "requires_approval": False,
        })
        steps.append({
            "key": "send-email",
            "name": "Send email",
            "action_type": "send_email",
            "params": {},
            "requires_approval": True,
        })
    elif "slack" in lowered:
        steps.append({
            "key": "compose-message",
            "name": "Compose Slack message with AI",
            "action_type": "ai_generate",
            "params": {"prompt": f"Compose a Slack message: {intent[:200]}"},
            "requires_approval": False,
        })
        steps.append({
            "key": "send-slack",
            "name": "Send Slack message",
            "action_type": "send_slack",
            "params": {},
            "requires_approval": True,
        })
    elif "lead" in lowered or "crm" in lowered or "follow" in lowered:
        steps.append({
            "key": "gather-leads",
            "name": "Gather lead context",
            "action_type": "fetch_calendar_digest",
            "params": {},
            "requires_approval": False,
        })
        steps.append({
            "key": "assign-followup",
            "name": "Assign follow-up task",
            "action_type": "create_task",
            "params": {"title": f"Follow up: {intent[:100]}"},
            "requires_approval": True,
        })
    elif "task" in lowered:
        steps.append({
            "key": "create-task",
            "name": "Create task",
            "action_type": "create_task",
            "params": {"title": intent[:200]},
            "requires_approval": True,
        })
    elif "calendar" in lowered or "meeting" in lowered or "schedule" in lowered:
        steps.append({
            "key": "check-calendar",
            "name": "Check calendar",
            "action_type": "fetch_calendar_digest",
            "params": {},
            "requires_approval": False,
        })
        steps.append({
            "key": "summarize",
            "name": "Summarize schedule",
            "action_type": "ai_generate",
            "params": {"prompt": f"Summarize and suggest: {intent[:200]}"},
            "requires_approval": False,
        })
    else:
        steps.append({
            "key": "analyze",
            "name": "Analyze request",
            "action_type": "ai_generate",
            "params": {"prompt": intent[:300]},
            "requires_approval": False,
        })
        steps.append({
            "key": "notify-owner",
            "name": "Notify owner",
            "action_type": "noop",
            "params": {"message": intent[:200]},
            "requires_approval": False,
        })

    return {
        "name": f"Workflow: {intent[:60]}",
        "summary": f"Auto-drafted workflow for: {intent[:160]}",
        "trigger_mode": "manual",
        "steps": steps,
        "risk_level": _infer_risk_level(steps),
        "confidence": 0.65,
        "workspace_id": workspace_id,
        "constraints": constraints,
        "available_integrations": available_integrations,
    }
