from __future__ import annotations

import re
from enum import StrEnum


class WorkflowDefinitionStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class WorkflowRunStatus(StrEnum):
    PENDING = "pending"
    AWAITING_APPROVAL = "awaiting_approval"
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    RETRY_WAIT = "retry_wait"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkflowStepRunStatus(StrEnum):
    PENDING = "pending"
    AWAITING_APPROVAL = "awaiting_approval"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class WorkflowStepDecision(StrEnum):
    SAFE_AUTO = "safe_auto"
    REQUIRES_APPROVAL = "requires_approval"
    BLOCKED = "blocked"


_ACTION_TYPE_RE = re.compile(r"^[a-z0-9_.-]{1,100}$")


def normalize_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return slug[:120] or "workflow"


def normalize_action_type(value: object) -> str:
    action_type = str(value or "").strip().lower()
    if not _ACTION_TYPE_RE.fullmatch(action_type):
        raise ValueError(f"Invalid action_type '{action_type}'")
    return action_type


def normalize_steps(steps_json: list[dict]) -> list[dict]:
    if not isinstance(steps_json, list) or not steps_json:
        raise ValueError("Workflow definition must include at least one step")
    if len(steps_json) > 20:
        raise ValueError("Workflow definition cannot exceed 20 steps")
    normalized: list[dict] = []
    for index, raw in enumerate(steps_json):
        if not isinstance(raw, dict):
            raise ValueError(f"Step {index} must be an object")
        params = raw.get("params") or {}
        if not isinstance(params, dict):
            raise ValueError(f"Step {index} params must be an object")
        name = str(raw.get("name") or f"step-{index + 1}").strip() or f"step-{index + 1}"
        normalized.append(
            {
                "key": str(raw.get("key") or normalize_slug(name) or f"step-{index + 1}")[:120],
                "name": name[:200],
                "action_type": normalize_action_type(raw.get("action_type")),
                "integration": str(raw.get("integration") or "").strip() or None,
                "params": dict(params),
                "requires_approval": bool(raw.get("requires_approval", False)),
            }
        )
    return normalized
