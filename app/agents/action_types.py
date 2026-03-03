from __future__ import annotations

CANONICAL_AGENT_ACTIONS: set[str] = {
    "NONE",
    "MEMORY_WRITE",
    "TASK_CREATE",
    "EMAIL_DRAFT",
    "SEND_MESSAGE",
    "SPEND_MONEY",
    "DELETE_DATA",
    "ASSIGN_LEADS",
    "CHANGE_CRM_STATUS",
}

_ALIASES: dict[str, str] = {
    "DRAFT_EMAIL": "EMAIL_DRAFT",
    "CREATE_TASK": "TASK_CREATE",
    "WRITE_MEMORY": "MEMORY_WRITE",
    "SEND_EMAIL": "SEND_MESSAGE",
}


def normalize_action_type(action_type: str | None) -> str:
    raw = str(action_type or "").strip().upper()
    if not raw:
        return "NONE"
    normalized = _ALIASES.get(raw, raw)
    return normalized
