"""Brain Engine drafting and proposal generation."""

import json
import logging

from pydantic import BaseModel, Field

from app.engines.brain.confidence import assess_agent_confidence
from app.engines.brain.router import call_ai
from app.schemas.brain_context import BrainContext

logger = logging.getLogger(__name__)


class AgentChatRequest(BaseModel):
    message: str = Field(..., max_length=10_000)
    force_role: str | None = Field(None, max_length=50)
    avatar_mode: str | None = Field(None, max_length=30)
    employee_id: int | None = Field(None, ge=1)
    provider: str | None = Field(None, max_length=20)


class ProposedAction(BaseModel):
    action_type: str
    params: dict = {}


class StepResult(BaseModel):
    step_number: int
    description: str
    role: str
    response: str
    requires_approval: bool
    proposed_actions: list[ProposedAction] = []


class MultiTurnResponse(BaseModel):
    steps: list[StepResult] = []
    final_summary: str = ""
    total_steps: int = 0
    steps_requiring_approval: int = 0
    all_proposed_actions: list[ProposedAction] = []
    confidence_score: int = 0
    confidence_level: str = "low"
    needs_human_review: bool = True


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


ROLE_PROMPTS: dict[str, str] = {
    "CEO Clone": (
        "You are Nidin's CEO Clone, his AI chief of staff and thinking partner.\n"
        "Your job: help Nidin prioritize, decide, delegate, and grow.\n"
        "Rules:\n"
        "- For business questions: respond with what the decision is, who should act, and whether approval is needed.\n"
        "- For personal or conversational messages: respond naturally with warmth and helpfulness.\n"
        "- When Nidin teaches you something or asks you to remember, acknowledge it and confirm what you learned.\n"
        "- Be direct. No fluff. Max 3 bullet points unless asked for more.\n"
        "- If an action is risky (sending messages, spending money, assigning work), flag it clearly.\n"
        "- You know Nidin runs a study abroad and recruitment company with about 23 staff.\n"
        "- Never reject a message as 'not applicable'. Always engage helpfully."
    ),
    "Ops Manager Clone": (
        "You are Nidin's Ops Manager Clone. You manage daily operations and team productivity.\n"
        "Your job: assign tasks, track blockers, manage daily plans for each team member.\n"
        "Rules:\n"
        "- Always respond with a specific task list, who is assigned, and what is blocked.\n"
        "- Use names and numbers, never be vague.\n"
        "- If you need to assign something, draft it and flag it for Nidin's approval.\n"
        "- Tech team: 1 Tech Head + 4 Developers. Manager: 1. Other teams: counsellors, app management, sub-agents."
    ),
    "Sales Lead Clone": (
        "You are Nidin's Sales Lead Clone. You manage leads and drive conversions.\n"
        "Your job: summarize lead status, identify who needs follow-up, and draft outreach.\n"
        "Rules:\n"
        "- Always respond with lead count, conversion context, and next action per segment.\n"
        "- Current conversion rate is about 5%. Focus on improving follow-up quality.\n"
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
        "- Be specific, give actual task names, not generic descriptions."
    ),
    "Strategist": (
        "You are Nidin's Strategist, his dedicated thinking partner for high-level decisions.\n"
        "Your job: help Nidin think through business strategy, market moves, competitive positioning, "
        "growth plans, partnerships, and long-term vision.\n"
        "Rules:\n"
        "- Always respond with structured strategic analysis.\n"
        "- When a decision is reached, state it clearly as: 'DECISION: <statement>'\n"
        "- Reference relevant context from past strategy sessions.\n"
        "- Push back on weak reasoning. Be the devil's advocate when needed.\n"
        "- Separate strategy from execution, execution belongs to the business agent."
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
    "strategy": (
        "Avatar mode: STRATEGY.\n"
        "You are Nidin's Strategy Partner, a senior strategic advisor.\n"
        "Your role: deep-think on business direction, market positioning, competitive moves, "
        "growth frameworks, and long-term planning.\n"
        "Rules:\n"
        "- Think in frameworks: SWOT, Porter's 5 Forces, OKRs, first-principles reasoning.\n"
        "- Challenge assumptions. Push Nidin to think bigger and more clearly.\n"
        "- When a decision is reached, prefix it with DECISION: so it can be extracted.\n"
        "- Reference past strategy sessions and decisions when relevant.\n"
        "- Never dilute strategic thinking with operational details, that's for the business agent.\n"
        "- Be direct, analytical, and structured. Use numbered lists for multi-part answers."
    ),
}

_INTENT_SYSTEM = (
    "You are an intent classifier. Given a user message, identify structured actions.\n"
    "Return a JSON array (only valid JSON, no markdown). Each element:\n"
    '  {"action_type": "<TYPE>", "params": {<key>: <value>}}\n'
    "Valid action_types: EMAIL_DRAFT, MEMORY_WRITE, TASK_CREATE, NONE\n"
    'For MEMORY_WRITE include params: {"key": "<topic>", "value": "<fact>"}\n'
    'For EMAIL_DRAFT include params: {"email_id": <int or null>}\n'
    'For TASK_CREATE include params: {"title": "<task name>"}\n'
    'If no clear action, return [{"action_type": "NONE", "params": {}}]\n'
    "Return ONLY the JSON array, nothing else."
)

_PLAN_SYSTEM = (
    "You are a task planner. Given a complex user request, break it into sequential steps.\n"
    "Return a JSON array where each element is:\n"
    '  {"step": <int>, "description": "<what to do>", "force_role": "<role or null>"}\n'
    "Valid roles: CEO Clone, Ops Manager Clone, Sales Lead Clone, Tech PM Clone\n"
    "If the request is simple (single action), return a single-step array.\n"
    "Maximum 5 steps. Return ONLY the JSON array, nothing else."
)


def route_role(message: str, force_role: str | None = None) -> str:
    """Pick the right clone role based on message content."""
    if force_role is not None and force_role in ROLE_PROMPTS:
        return force_role
    text = message.lower()
    if any(token in text for token in ("lead", "follow-up", "conversion", "sales", "prospect")):
        return "Sales Lead Clone"
    if any(token in text for token in ("task", "staff", "ops", "daily plan", "team", "productivity")):
        return "Ops Manager Clone"
    if any(token in text for token in ("roadmap", "spec", "bug", "release", "developer", "sprint", "code")):
        return "Tech PM Clone"
    return "CEO Clone"


async def extract_proposed_actions(
    message: str,
    organization_id: int | None = None,
    brain_context: BrainContext | None = None,
) -> list[ProposedAction]:
    """Extract structured actions from a user message."""
    raw = await call_ai(
        system_prompt=_INTENT_SYSTEM,
        user_message=message[:1000],
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


async def run_agent(
    request: AgentChatRequest,
    memory_context: str = "",
    conversation_history: list[dict] | None = None,
    organization_id: int | None = None,
    brain_context: BrainContext | None = None,
) -> AgentChatResponse:
    """Route the request to the appropriate role and generate a response."""
    avatar_key = (request.avatar_mode or "professional").strip().lower()
    if avatar_key not in AVATAR_PROMPTS:
        avatar_key = "professional"

    if avatar_key == "strategy":
        role = "Strategist"
        effective_provider: str | None = "openai"
    else:
        role = route_role(request.message, request.force_role)
        effective_provider = request.provider

    system_prompt = f"{AVATAR_PROMPTS[avatar_key]}\n\n{ROLE_PROMPTS[role]}"

    response_text = await call_ai(
        system_prompt=system_prompt,
        user_message=request.message,
        memory_context=memory_context,
        conversation_history=conversation_history,
        organization_id=organization_id,
        brain_context=brain_context,
        provider=effective_provider,
    )

    requires_approval = any(token in request.message.lower() for token in _RISKY_TOKENS)
    actions = await extract_proposed_actions(
        message=request.message,
        organization_id=organization_id,
        brain_context=brain_context,
    )
    actions = [action for action in actions if action.action_type != "NONE"]

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


async def _decompose_plan(
    message: str,
    organization_id: int | None = None,
    brain_context: BrainContext | None = None,
) -> list[dict]:
    """Break a complex request into sequential steps."""
    raw = await call_ai(
        system_prompt=_PLAN_SYSTEM,
        user_message=message[:2000],
        organization_id=organization_id,
        brain_context=brain_context,
    )
    try:
        items = json.loads(raw or "[]")
        if not isinstance(items, list):
            return [{"step": 1, "description": message, "force_role": None}]
        return items[:5]
    except (json.JSONDecodeError, TypeError, ValueError):
        return [{"step": 1, "description": message, "force_role": None}]


async def run_agent_multi_turn(
    request: AgentChatRequest,
    memory_context: str = "",
    conversation_history: list[dict] | None = None,
    organization_id: int | None = None,
    brain_context: BrainContext | None = None,
) -> MultiTurnResponse:
    """Decompose a complex request into multiple step executions."""
    plan = await _decompose_plan(
        message=request.message,
        organization_id=organization_id,
        brain_context=brain_context,
    )

    if len(plan) <= 1:
        result = await run_agent(
            request=request,
            memory_context=memory_context,
            conversation_history=conversation_history,
            organization_id=organization_id,
            brain_context=brain_context,
        )
        step = StepResult(
            step_number=1,
            description=request.message,
            role=result.role,
            response=result.response,
            requires_approval=result.requires_approval,
            proposed_actions=result.proposed_actions,
        )
        return MultiTurnResponse(
            steps=[step],
            final_summary=result.response,
            total_steps=1,
            steps_requiring_approval=int(result.requires_approval),
            all_proposed_actions=result.proposed_actions,
            confidence_score=result.confidence_score,
            confidence_level=result.confidence_level,
            needs_human_review=result.needs_human_review,
        )

    steps: list[StepResult] = []
    all_actions: list[ProposedAction] = []
    approval_count = 0
    running_history = list(conversation_history or [])

    for item in plan:
        step_num = int(item.get("step", len(steps) + 1))
        description = str(item.get("description", ""))
        force_role = item.get("force_role")

        step_request = AgentChatRequest(
            message=description,
            force_role=force_role if force_role in ROLE_PROMPTS else None,
            avatar_mode=request.avatar_mode,
            employee_id=request.employee_id,
            provider=request.provider,
        )

        result = await run_agent(
            request=step_request,
            memory_context=memory_context,
            conversation_history=running_history or None,
            organization_id=organization_id,
            brain_context=brain_context,
        )

        step = StepResult(
            step_number=step_num,
            description=description,
            role=result.role,
            response=result.response,
            requires_approval=result.requires_approval,
            proposed_actions=result.proposed_actions,
        )
        steps.append(step)
        all_actions.extend(result.proposed_actions)
        if result.requires_approval:
            approval_count += 1

        running_history.append({"role": "user", "content": description})
        running_history.append({"role": "assistant", "content": result.response})

    final = steps[-1].response if steps else ""
    confidence = assess_agent_confidence(
        user_message=request.message,
        ai_response=final,
        requires_approval=approval_count > 0,
        memory_context=memory_context,
        proposed_actions_count=len(all_actions),
    )

    return MultiTurnResponse(
        steps=steps,
        final_summary=final,
        total_steps=len(steps),
        steps_requiring_approval=approval_count,
        all_proposed_actions=all_actions,
        confidence_score=confidence.score,
        confidence_level=confidence.level,
        needs_human_review=confidence.needs_human_review,
    )
