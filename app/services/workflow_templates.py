"""Built-in workflow template presets for common automation patterns.

Templates are static definitions that can be instantiated as draft
WorkflowDefinitions with one click. Each template provides a pre-built
step sequence that users can customize before publishing.
"""
from __future__ import annotations

_TEMPLATES: list[dict] = [
    {
        "id": "lead-follow-up",
        "name": "Lead Follow-Up Sequence",
        "description": "Automatically follow up with new leads: fetch context, draft email, request approval, then send.",
        "category": "sales",
        "trigger_mode": "signal",
        "risk_level": "medium",
        "steps": [
            {"key": "fetch-context", "name": "Fetch lead context", "action_type": "fetch_calendar_digest", "params": {}, "requires_approval": False},
            {"key": "draft-email", "name": "AI draft follow-up email", "action_type": "ai_generate", "params": {"prompt_template": "draft_lead_followup"}, "requires_approval": False},
            {"key": "review", "name": "Manager review", "action_type": "noop", "params": {}, "requires_approval": True},
            {"key": "send-email", "name": "Send email", "action_type": "send_email", "params": {}, "requires_approval": False},
        ],
    },
    {
        "id": "daily-briefing",
        "name": "Daily Morning Briefing",
        "description": "Generate and send a daily briefing: calendar digest, task summary, and risk alerts via Slack.",
        "category": "operations",
        "trigger_mode": "scheduled",
        "risk_level": "low",
        "steps": [
            {"key": "calendar", "name": "Fetch calendar digest", "action_type": "fetch_calendar_digest", "params": {}, "requires_approval": False},
            {"key": "tasks", "name": "Summarize open tasks", "action_type": "ai_generate", "params": {"prompt_template": "daily_task_summary"}, "requires_approval": False},
            {"key": "notify", "name": "Send to Slack", "action_type": "send_slack", "params": {"channel": "#daily-briefing"}, "requires_approval": False},
        ],
    },
    {
        "id": "contact-scoring",
        "name": "Batch Contact Scoring",
        "description": "Rescore all contacts using AI intelligence, then alert on hot leads.",
        "category": "sales",
        "trigger_mode": "scheduled",
        "risk_level": "low",
        "steps": [
            {"key": "score", "name": "Batch score contacts", "action_type": "ai_generate", "params": {"prompt_template": "batch_contact_score"}, "requires_approval": False},
            {"key": "alert", "name": "Alert on hot leads", "action_type": "send_slack", "params": {"channel": "#hot-leads"}, "requires_approval": False},
        ],
    },
    {
        "id": "approval-chain",
        "name": "Multi-Level Approval Chain",
        "description": "Route a request through manager review, then director approval, with notifications at each step.",
        "category": "governance",
        "trigger_mode": "manual",
        "risk_level": "high",
        "steps": [
            {"key": "notify-manager", "name": "Notify manager", "action_type": "send_slack", "params": {"channel": "#approvals"}, "requires_approval": False},
            {"key": "manager-review", "name": "Manager approval", "action_type": "noop", "params": {}, "requires_approval": True},
            {"key": "notify-director", "name": "Notify director", "action_type": "send_email", "params": {}, "requires_approval": False},
            {"key": "director-review", "name": "Director approval", "action_type": "noop", "params": {}, "requires_approval": True},
            {"key": "execute", "name": "Execute approved action", "action_type": "http_request", "params": {}, "requires_approval": False},
        ],
    },
    {
        "id": "new-client-onboarding",
        "name": "New Client Onboarding",
        "description": "Onboard a new client: create task list, send welcome email, schedule kickoff call, notify team.",
        "category": "operations",
        "trigger_mode": "manual",
        "risk_level": "medium",
        "steps": [
            {"key": "create-tasks", "name": "Create onboarding tasks", "action_type": "create_task", "params": {"task_template": "client_onboarding"}, "requires_approval": False},
            {"key": "welcome-email", "name": "Send welcome email", "action_type": "send_email", "params": {}, "requires_approval": True},
            {"key": "schedule-call", "name": "Schedule kickoff call", "action_type": "fetch_calendar_digest", "params": {}, "requires_approval": False},
            {"key": "notify-team", "name": "Notify team on Slack", "action_type": "send_slack", "params": {"channel": "#new-clients"}, "requires_approval": False},
        ],
    },
    {
        "id": "weekly-report",
        "name": "Weekly Performance Report",
        "description": "Generate a weekly report: aggregate metrics, AI summary, send to stakeholders.",
        "category": "reporting",
        "trigger_mode": "scheduled",
        "risk_level": "low",
        "steps": [
            {"key": "metrics", "name": "Aggregate weekly metrics", "action_type": "ai_generate", "params": {"prompt_template": "weekly_metrics"}, "requires_approval": False},
            {"key": "summary", "name": "AI executive summary", "action_type": "ai_generate", "params": {"prompt_template": "weekly_exec_summary"}, "requires_approval": False},
            {"key": "send", "name": "Email report to stakeholders", "action_type": "send_email", "params": {}, "requires_approval": True},
        ],
    },
]


def get_templates() -> list[dict]:
    """Return all available workflow templates."""
    return [
        {
            "id": t["id"],
            "name": t["name"],
            "description": t["description"],
            "category": t["category"],
            "trigger_mode": t["trigger_mode"],
            "risk_level": t["risk_level"],
            "step_count": len(t["steps"]),
        }
        for t in _TEMPLATES
    ]


def get_template_by_id(template_id: str) -> dict | None:
    """Get a single template by ID, including full step details."""
    for t in _TEMPLATES:
        if t["id"] == template_id:
            return t
    return None
