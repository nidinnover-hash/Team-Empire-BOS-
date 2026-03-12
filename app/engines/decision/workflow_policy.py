from __future__ import annotations

from app.domains.automation.models import WorkflowStepDecision

SAFE_AUTO_ACTIONS = {
    "noop",
    "unknown_noop",
    "fetch_calendar_digest",
}

BLOCKED_ACTION_PREFIXES = ("admin.", "root.", "system.delete")


def evaluate_workflow_step_policy(*, step: dict) -> tuple[WorkflowStepDecision, str]:
    action_type = str(step.get("action_type") or "").strip().lower()

    # Hard block missing or obviously invalid action types
    if not action_type:
        return (WorkflowStepDecision.BLOCKED, "missing_action_type")
    if len(action_type) > 128:
        return (WorkflowStepDecision.BLOCKED, "action_type_too_long")

    if any(action_type.startswith(prefix) for prefix in BLOCKED_ACTION_PREFIXES):
        return (WorkflowStepDecision.BLOCKED, "action_type_blocked")
    if bool(step.get("requires_approval")):
        return (WorkflowStepDecision.REQUIRES_APPROVAL, "step_marked_requires_approval")
    if action_type in SAFE_AUTO_ACTIONS or action_type.startswith("fetch_") or action_type.startswith("read_"):
        return (WorkflowStepDecision.SAFE_AUTO, "read_only_or_safe_action")
    return (WorkflowStepDecision.REQUIRES_APPROVAL, "mutating_default_requires_approval")
