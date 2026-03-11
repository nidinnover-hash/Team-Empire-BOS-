"""Unit tests for workflow step policy: blocked action types, safe auto, requires approval."""

from app.domains.automation.models import WorkflowStepDecision
from app.engines.decision.workflow_policy import evaluate_workflow_step_policy


def test_empty_action_type_blocked():
    decision, reason = evaluate_workflow_step_policy(step={"action_type": ""})
    assert decision == WorkflowStepDecision.BLOCKED
    assert reason == "missing_action_type"


def test_none_action_type_blocked():
    decision, reason = evaluate_workflow_step_policy(step={})
    assert decision == WorkflowStepDecision.BLOCKED
    assert reason == "missing_action_type"


def test_action_type_too_long_blocked():
    decision, reason = evaluate_workflow_step_policy(step={"action_type": "x" * 129})
    assert decision == WorkflowStepDecision.BLOCKED
    assert reason == "action_type_too_long"


def test_blocked_prefix_admin_blocked():
    decision, reason = evaluate_workflow_step_policy(step={"action_type": "admin.delete_user"})
    assert decision == WorkflowStepDecision.BLOCKED
    assert reason == "action_type_blocked"


def test_blocked_prefix_root_blocked():
    decision, reason = evaluate_workflow_step_policy(step={"action_type": "root.shell"})
    assert decision == WorkflowStepDecision.BLOCKED
    assert reason == "action_type_blocked"


def test_blocked_prefix_system_delete_blocked():
    decision, reason = evaluate_workflow_step_policy(step={"action_type": "system.delete"})
    assert decision == WorkflowStepDecision.BLOCKED
    assert reason == "action_type_blocked"


def test_safe_auto_fetch_calendar_digest():
    decision, reason = evaluate_workflow_step_policy(step={"action_type": "fetch_calendar_digest"})
    assert decision == WorkflowStepDecision.SAFE_AUTO
    assert "read_only" in reason or "safe" in reason


def test_safe_auto_fetch_prefix():
    decision, reason = evaluate_workflow_step_policy(step={"action_type": "fetch_anything"})
    assert decision == WorkflowStepDecision.SAFE_AUTO


def test_safe_auto_read_prefix():
    decision, reason = evaluate_workflow_step_policy(step={"action_type": "read_contacts"})
    assert decision == WorkflowStepDecision.SAFE_AUTO


def test_safe_auto_noop():
    decision, reason = evaluate_workflow_step_policy(step={"action_type": "noop"})
    assert decision == WorkflowStepDecision.SAFE_AUTO


def test_requires_approval_when_step_marked():
    decision, reason = evaluate_workflow_step_policy(
        step={"action_type": "send_email", "requires_approval": True}
    )
    assert decision == WorkflowStepDecision.REQUIRES_APPROVAL
    assert reason == "step_marked_requires_approval"


def test_mutating_default_requires_approval():
    decision, reason = evaluate_workflow_step_policy(step={"action_type": "send_email"})
    assert decision == WorkflowStepDecision.REQUIRES_APPROVAL
    assert reason == "mutating_default_requires_approval"
