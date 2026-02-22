from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.orchestrator import AgentChatRequest, AgentChatResponse, run_agent
from app.core.deps import get_db
from app.core.rbac import require_roles
from app.logs.audit import record_action
from app.services import memory as memory_service
from app.services.memory import build_memory_context

router = APIRouter(prefix="/agents", tags=["Agents"])


@router.post("/chat", response_model=AgentChatResponse)
async def agent_chat(
    data: AgentChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF")),
) -> AgentChatResponse:
    """
    Send a message to your AI clone. Returns a real AI response.

    The clone automatically picks the right role (CEO, Ops, Sales, Tech PM)
    based on your message, or you can force a role with force_role.
    """
    # Build memory context from profile, team, and today's priorities
    org_id = int(current_user.get("org_id", 1))
    memory_context = await build_memory_context(db, organization_id=org_id)

    result = await run_agent(request=data, memory_context=memory_context)

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
            "proposed_actions_count": len(result.proposed_actions),
            "memory_write_requested": should_persist_memory,
            "memory_write_count": memory_written_count,
        },
        organization_id=org_id,
    )

    return result
