"""
Agent Orchestrator — routes messages to the right clone role and calls real AI.

Roles:
  CEO Clone        → strategy, priorities, high-level decisions
  Ops Manager Clone → daily tasks, team management, blockers
  Sales Lead Clone  → leads, follow-ups, conversion actions
  Tech PM Clone     → developer tasks, sprint planning, technical decisions
"""

import json

from pydantic import BaseModel, Field

from app.schemas.brain_context import BrainContext
from app.services.ai_router import call_ai
from app.services.confidence import assess_agent_confidence

# ── Schemas ───────────────────────────────────────────────────────────────────

class AgentChatRequest(BaseModel):
    message: str = Field(..., max_length=10_000)
    force_role: str | None = Field(None, max_length=50)
    avatar_mode: str | None = Field(None, max_length=30)
    employee_id: int | None = Field(None, ge=1)


class ProposedAction(BaseModel):
    action_type: str  # EMAIL_DRAFT | MEMORY_WRITE | TASK_CREATE | NONE
    params: dict = {}


class AgentChatResponse(BaseModel):
    role: str
    response: str
    requires_approval: bool
    proposed_actions: list[ProposedAction] = []
    confidence_score: int = 0
    confidence_level: str = "low"
    confidence_reasons: list[str] = []
    needs_human_review: bool = True
    memory_context_chars: int = 0
    memory_context_truncated: bool = False
    memory_sources: list[str] = []
    memory_source_counts: dict[str, int] = {}
    policy_score: int = 100
    blocked_by_policy: bool = False
    policy_reasons: list[str] = []
    policy_blocked_actions: list[str] = []
    policy_matched_rule_ids: list[int] = []


# ── Role System Prompts ───────────────────────────────────────────────────────

ROLE_PROMPTS: dict[str, str] = {
    "CEO Clone": (
        "You are Nidin's CEO Clone. You think strategically and make high-level decisions.\n"
        "Your job: help Nidin prioritize, decide, and delegate — not execute.\n"
        "Rules:\n"
        "- Always respond with what the decision is, who should act on it, and whether approval is needed.\n"
        "- Be direct. No fluff. Max 3 bullet points unless asked for more.\n"
        "- If an action is risky (sending messages, spending money, assigning work), flag it clearly.\n"
        "- You know Nidin runs a study abroad and recruitment company with ~23 staff."
    ),
    "Ops Manager Clone": (
        "You are Nidin's Ops Manager Clone. You manage daily operations and team productivity.\n"
        "Your job: assign tasks, track blockers, manage daily plans for each team member.\n"
        "Rules:\n"
        "- Always respond with a specific task list, who is assigned, and what is blocked.\n"
        "- Use names and numbers — never be vague.\n"
        "- If you need to assign something, draft it and flag it for Nidin's approval.\n"
        "- Tech team: 1 Tech Head + 4 Developers. Manager: 1. Other teams: counsellors, app management, sub-agents."
    ),
    "Sales Lead Clone": (
        "You are Nidin's Sales Lead Clone. You manage leads and drive conversions.\n"
        "Your job: summarize lead status, identify who needs follow-up, and draft outreach.\n"
        "Rules:\n"
        "- Always respond with lead count, conversion context, and next action per segment.\n"
        "- Current conversion rate is ~5%. Focus on improving follow-up quality.\n"
        "- Leads come through social media and manual collection.\n"
        "- Never send messages without Nidin's approval."
    ),
    "Tech PM Clone": (
        "You are Nidin's Tech PM Clone. You manage the tech team and technical decisions.\n"
        "Your job: convert goals into developer tasks, track sprint progress, flag risks.\n"
        "Rules:\n"
        "- Always respond with: current task status, next tasks to assign, any blockers.\n"
        "- Tech team has 1 Tech Head and 4 developers. They currently track work in Excel.\n"
        "- Prioritize tasks that directly move active projects forward.\n"
        "- Be specific — give actual task names, not generic descriptions."
    ),
}

_RISKY_TOKENS = ("send", "assign", "change", "spend", "delete", "fire", "hire", "pay")

AVATAR_PROMPTS: dict[str, str] = {
    "personal": (
        "Avatar mode: PERSONAL.\n"
        "Speak with warmth, empathy, and relationship-first framing.\n"
        "Focus on life alignment, stress reduction, confidence, and growth.\n"
        "Keep advice practical and kind. Avoid harsh corporate tone."
    ),
    "professional": (
        "Avatar mode: PROFESSIONAL.\n"
        "Use precise executive language with measurable outcomes.\n"
        "Focus on priorities, ownership, deadlines, and risk controls.\n"
        "Keep responses concise, action-oriented, and business strict."
    ),
    "entertainment": (
        "Avatar mode: ENTERTAINMENT.\n"
        "Be creative, energetic, and fun while staying safe and respectful.\n"
        "Focus on storytelling, hooks, scripts, campaign ideas, and audience excitement.\n"
        "Entertainment channels are restricted to YouTube and Audible contexts.\n"
        "Avoid mixing confidential operational decisions into this mode."
    ),
}


# ── Role Router ───────────────────────────────────────────────────────────────

def route_role(message: str, force_role: str | None = None) -> str:
    """Pick the right clone role based on message content."""
    if force_role is not None and force_role in ROLE_PROMPTS:
        return force_role
    # Unknown force_role falls through to keyword routing (no KeyError)
    text = message.lower()
    if any(t in text for t in ("lead", "follow-up", "conversion", "sales", "prospect")):
        return "Sales Lead Clone"
    if any(t in text for t in ("task", "staff", "ops", "daily plan", "team", "productivity")):
        return "Ops Manager Clone"
    if any(t in text for t in ("roadmap", "spec", "bug", "release", "developer", "sprint", "code")):
        return "Tech PM Clone"
    return "CEO Clone"


# ── Intent Extraction ─────────────────────────────────────────────────────────

_INTENT_SYSTEM = (
    "You are an intent classifier. Given a user message, identify structured actions.\n"
    "Return a JSON array (only valid JSON, no markdown). Each element:\n"
    "  {\"action_type\": \"<TYPE>\", \"params\": {<key>: <value>}}\n"
    "Valid action_types: EMAIL_DRAFT, MEMORY_WRITE, TASK_CREATE, NONE\n"
    "For MEMORY_WRITE include params: {\"key\": \"<topic>\", \"value\": \"<fact>\"}\n"
    "For EMAIL_DRAFT include params: {\"email_id\": <int or null>}\n"
    "For TASK_CREATE include params: {\"title\": \"<task name>\"}\n"
    "If no clear action, return [{\"action_type\": \"NONE\", \"params\": {}}]\n"
    "Return ONLY the JSON array, nothing else."
)


async def extract_proposed_actions(
    message: str,
    organization_id: int | None = None,
    brain_context: BrainContext | None = None,
) -> list[ProposedAction]:
    """
    Second cheap AI call to extract structured intent from the user message.
    Returns a list of ProposedAction objects; falls back to [NONE] on any error.
    """
    raw = await call_ai(
        system_prompt=_INTENT_SYSTEM,
        user_message=message[:1000],  # cap to keep the call cheap
        organization_id=organization_id,
        brain_context=brain_context,
    )
    try:
        items = json.loads(raw or "[]")
        if not isinstance(items, list):
            return []
        return [
            ProposedAction(**item)
            for item in items
            if isinstance(item, dict) and "action_type" in item
        ]
    except (json.JSONDecodeError, TypeError, ValueError):
        return []


# ── Main Agent Function ───────────────────────────────────────────────────────

async def run_agent(
    request: AgentChatRequest,
    memory_context: str = "",
    conversation_history: list[dict] | None = None,
    organization_id: int | None = None,
    brain_context: BrainContext | None = None,
) -> AgentChatResponse:
    """
    Route the message to the right role and get a real AI response.

    Args:
        request:              The user's message + optional forced role.
        memory_context:       Injected memory string (profile + team + daily context).
        conversation_history: Recent turns in OpenAI message format for multi-turn context.

    Returns:
        AgentChatResponse with role, AI response, approval flag, and proposed_actions.
    """
    role = route_role(request.message, request.force_role)
    avatar_key = (request.avatar_mode or "professional").strip().lower()
    if avatar_key not in AVATAR_PROMPTS:
        avatar_key = "professional"
    system_prompt = f"{AVATAR_PROMPTS[avatar_key]}\n\n{ROLE_PROMPTS[role]}"

    response_text = await call_ai(
        system_prompt=system_prompt,
        user_message=request.message,
        memory_context=memory_context,
        conversation_history=conversation_history,
        organization_id=organization_id,
        brain_context=brain_context,
    )

    requires_approval = any(t in request.message.lower() for t in _RISKY_TOKENS)

    # Keep the main chat path single-call for latency and cost stability.
    actions: list[ProposedAction] = []

    confidence = assess_agent_confidence(
        user_message=request.message,
        ai_response=response_text,
        requires_approval=requires_approval,
        memory_context=memory_context,
        proposed_actions_count=len(actions),
    )

    return AgentChatResponse(
        role=role,
        response=response_text,
        requires_approval=requires_approval,
        proposed_actions=actions,
        confidence_score=confidence.score,
        confidence_level=confidence.level,
        confidence_reasons=confidence.reasons,
        needs_human_review=confidence.needs_human_review,
    )
