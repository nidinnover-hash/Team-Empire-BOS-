from collections import Counter

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.action_types import CANONICAL_AGENT_ACTIONS, normalize_action_type
from app.agents.orchestrator import AgentChatRequest, AgentChatResponse, run_agent
from app.core.deps import get_db
from app.core.rbac import require_roles
from app.logs.audit import record_action
from app.schemas.task import TaskCreate
from app.services import email_service
from app.services import memory as memory_service
from app.services import task as task_service
from app.services.agent_policy import evaluate_agent_policy
from app.services.context_builder import build_brain_context
from app.services.memory import build_memory_context

router = APIRouter(prefix="/agents", tags=["Agents"])


def _memory_attribution(memory_context: str) -> tuple[list[str], dict[str, int], bool]:
    """Extract simple source attribution signals from the injected memory context."""
    if not memory_context:
        return [], {}, False
    markers = {
        "PROFILE:": "profile",
        "TEAM (": "team",
        "TEAM:": "team",
        "TODAY'S CONTEXT:": "daily_context",
        "INTEGRATIONS:": "integrations",
        "[CLICKUP OPEN TASKS]": "clickup",
        "[GITHUB DEV ACTIVITY]": "github",
        "[SECURITY POSTURE]": "security",
        "[STRIPE FINANCIALS]": "stripe",
        "[CALENDLY TODAY]": "calendly",
        "[CHARACTER PROFILE]": "character_profile",
    }
    counts: Counter[str] = Counter()
    for line in memory_context.splitlines():
        stripped = line.strip()
        for prefix, label in markers.items():
            if stripped.startswith(prefix):
                counts[label] += 1
    truncated = (
        "[... memory truncated for length ...]" in memory_context
        or "... (memory truncated)" in memory_context
    )
    sources = sorted(counts.keys())
    return sources, dict(counts), truncated


@router.post("/chat", response_model=AgentChatResponse)
async def agent_chat(
    data: AgentChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF")),
) -> AgentChatResponse:
    """
    Send a message to your AI agent. Returns a real AI response.

    The agent automatically picks the right role (CEO, Ops, Sales, Tech PM)
    based on your message, or you can force a role with force_role.
    """
    # Only CEO/ADMIN may force a specific role; other roles get keyword routing
    if data.force_role and current_user["role"] not in {"CEO", "ADMIN"}:
        data.force_role = None
    if data.employee_id and current_user["role"] not in {"CEO", "ADMIN", "MANAGER"}:
        data.employee_id = None

    # Build memory context from profile, team, and today's priorities
    org_id = int(current_user["org_id"])
    brain_context = await build_brain_context(
        db,
        organization_id=org_id,
        actor_user_id=int(current_user["id"]),
        actor_role=str(current_user["role"]),
        request_purpose=str(current_user.get("purpose") or "professional"),
        employee_id=data.employee_id,
    )
    memory_context = await build_memory_context(db, organization_id=org_id)

    result = await run_agent(
        request=data,
        memory_context=memory_context,
        organization_id=org_id,
        brain_context=brain_context,
    )
    unknown_actions: list[str] = []
    for action in result.proposed_actions:
        normalized = normalize_action_type(action.action_type)
        if normalized not in CANONICAL_AGENT_ACTIONS:
            unknown_actions.append(str(action.action_type))
            action.action_type = "NONE"
            continue
        action.action_type = normalized
    policy_eval = await evaluate_agent_policy(
        db,
        organization_id=org_id,
        message=data.message,
        proposed_actions=[a.action_type for a in result.proposed_actions],
    )
    blocked_actions = set(policy_eval["blocked_actions"])
    if blocked_actions:
        result.proposed_actions = [
            action for action in result.proposed_actions
            if action.action_type not in blocked_actions
        ]
    result.policy_score = policy_eval["policy_score"]
    result.blocked_by_policy = policy_eval["blocked_by_policy"]
    result.policy_reasons = policy_eval["reasons"]
    result.policy_blocked_actions = policy_eval["blocked_actions"]
    result.policy_matched_rule_ids = policy_eval["matched_rule_ids"]
    if unknown_actions:
        result.blocked_by_policy = True
        result.policy_reasons = [*result.policy_reasons, "Unknown action types blocked by default."][:6]
        result.policy_blocked_actions = sorted(set(result.policy_blocked_actions + unknown_actions))
    memory_sources, memory_source_counts, memory_context_truncated = _memory_attribution(memory_context)
    result.memory_context_chars = len(memory_context)
    result.memory_context_truncated = memory_context_truncated
    result.memory_sources = memory_sources
    result.memory_source_counts = memory_source_counts
    # Explicit-memory rule: only write memory when user intentionally says "remember".
    lowered = data.message.lower()
    should_persist_memory = ("remember" in lowered) or ("remember this" in lowered)
    memory_written_count = 0
    if should_persist_memory and current_user.get("role") in {"CEO", "ADMIN"}:
        for action in result.proposed_actions:
            if action.action_type != "MEMORY_WRITE":
                continue
            key = (action.params or {}).get("key")
            value = (action.params or {}).get("value")
            if isinstance(key, str) and key.strip() and isinstance(value, str) and value.strip():
                entry = await memory_service.upsert_profile_memory(
                    db=db,
                    organization_id=org_id,
                    key=key.strip(),
                    value=value.strip(),
                    category="assistant",
                )
                await record_action(
                    db=db,
                    event_type="agent_memory_written",
                    actor_user_id=int(current_user["id"]),
                    entity_type="profile_memory",
                    entity_id=entry.id,
                    payload_json={"key": key.strip()},
                    organization_id=org_id,
                )
                memory_written_count += 1
        if memory_written_count == 0:
            await record_action(
                db=db,
                event_type="agent_memory_write_skipped",
                actor_user_id=int(current_user["id"]),
                entity_type="agent",
                entity_id=None,
                payload_json={"reason": "no_valid_memory_actions"},
                organization_id=org_id,
            )
    elif should_persist_memory:
        await record_action(
            db=db,
            event_type="agent_memory_write_skipped",
            actor_user_id=int(current_user["id"]),
            entity_type="agent",
            entity_id=None,
            payload_json={"reason": "role_not_allowed"},
            organization_id=org_id,
        )

    # TASK_CREATE — executes when user explicitly asks to create a task
    should_create_task = any(kw in lowered for kw in ("create task", "add task", "make task"))
    tasks_created = 0
    if should_create_task and current_user.get("role") in {"CEO", "ADMIN", "MANAGER"}:
        for action in result.proposed_actions:
            if action.action_type != "TASK_CREATE":
                continue
            title = (action.params or {}).get("title")
            if isinstance(title, str) and title.strip():
                new_task = await task_service.create_task(
                    db,
                    TaskCreate(title=title.strip()),  # type: ignore[call-arg]
                    organization_id=org_id,
                )
                await record_action(
                    db=db,
                    event_type="agent_task_created",
                    actor_user_id=int(current_user["id"]),
                    entity_type="task",
                    entity_id=new_task.id,
                    payload_json={"title": title.strip(), "source": "agent_chat"},
                    organization_id=org_id,
                )
                tasks_created += 1

    # EMAIL_DRAFT — executes when user explicitly asks to draft an email reply.
    # draft_reply() always creates an approval request — nothing is sent without human approval.
    should_draft_email = any(kw in lowered for kw in ("draft reply", "draft email", "draft a reply", "write a reply"))
    email_drafts_created = 0
    if should_draft_email and current_user.get("role") in {"CEO", "ADMIN"}:
        for action in result.proposed_actions:
            if action.action_type != "EMAIL_DRAFT":
                continue
            email_id = (action.params or {}).get("email_id")
            if isinstance(email_id, int):
                draft = await email_service.draft_reply(
                    db=db,
                    email_id=email_id,
                    org_id=org_id,
                    actor_user_id=int(current_user["id"]),
                )
                if draft:
                    await record_action(
                        db=db,
                        event_type="agent_email_draft_created",
                        actor_user_id=int(current_user["id"]),
                        entity_type="email",
                        entity_id=email_id,
                        payload_json={"email_id": email_id, "source": "agent_chat"},
                        organization_id=org_id,
                    )
                    email_drafts_created += 1

    # Log the interaction
    await record_action(
        db=db,
        event_type="agent_chat",
        actor_user_id=int(current_user["id"]),
        entity_type="agent",
        entity_id=None,
        payload_json={
            "role": result.role,
            "message": data.message,
            "requires_approval": result.requires_approval,
            "confidence_score": result.confidence_score,
            "confidence_level": result.confidence_level,
            "needs_human_review": result.needs_human_review,
            "proposed_actions_count": len(result.proposed_actions),
            "memory_write_requested": should_persist_memory,
            "memory_write_count": memory_written_count,
            "tasks_created": tasks_created,
            "email_drafts_created": email_drafts_created,
            "policy_score": result.policy_score,
            "blocked_by_policy": result.blocked_by_policy,
            "policy_blocked_actions": result.policy_blocked_actions,
        },
        organization_id=org_id,
    )

    return result
