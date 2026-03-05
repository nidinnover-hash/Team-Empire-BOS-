"""Web chat routes: agent chat, chat history, daily run trigger."""

import logging

from fastapi import APIRouter, Depends, Form, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_web_user, get_db, verify_csrf
from app.services import memory as memory_service
from app.services import talk_commands as talk_command_service
from app.services.context_builder import build_brain_context
from app.web._helpers import read_avatar_scope, write_avatar_scope

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Web Chat"])


@router.post("/web/agents/chat")
async def web_agent_chat(
    message: str = Form(..., max_length=10_000),
    force_role: str | None = Form(None, max_length=50),
    avatar_mode: str | None = Form(None, max_length=30),
    _csrf_ok: None = Depends(verify_csrf),
    user: dict = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    from app.agents.orchestrator import AgentChatRequest, run_agent
    from app.services import chat_history as chat_history_service
    from app.services import conversation_learning as conversation_learning_service
    from app.services.memory import build_memory_context

    # Only CEO/ADMIN may force a specific role; other roles get keyword routing
    if force_role and user["role"] not in {"CEO", "ADMIN"}:
        force_role = None
    default_avatar = str(user.get("default_avatar_mode") or "professional")
    avatar_mode = (avatar_mode or default_avatar).strip().lower()
    if avatar_mode not in {"personal", "professional", "entertainment", "strategy"}:
        avatar_mode = "professional"
    # Strategy mode is CEO/ADMIN only
    if avatar_mode == "strategy" and user["role"] not in {"CEO", "ADMIN"}:
        avatar_mode = "professional"
    read_mode = read_avatar_scope(user, avatar_mode)
    write_mode = write_avatar_scope(user, avatar_mode)

    org_id = int(user["org_id"])
    brain_context = await build_brain_context(
        db,
        organization_id=org_id,
        actor_user_id=int(user["id"]),
        actor_role=str(user["role"]),
        request_purpose=str(user.get("purpose") or "professional"),
    )
    memory_context = await build_memory_context(
        db,
        organization_id=org_id,
        categories=(
            None
            if read_mode == "professional"
            else ["identity", "preference", "learned", "personal", "entertainment"]
        ),
    )
    avatar_memories = await memory_service.get_avatar_memory(
        db, organization_id=org_id, avatar_mode=read_mode,
    )
    if avatar_memories:
        avatar_block = "\n".join(f"- {item.key}: {item.value}" for item in avatar_memories[:30])
        memory_context = f"{memory_context}\n\n[AVATAR:{read_mode.upper()}]\n{avatar_block}"

    # Load the last 10 turns for multi-turn context
    recent = await chat_history_service.get_recent(
        db, org_id=org_id, limit=10, avatar_mode=read_mode,
    )
    history = chat_history_service.as_openai_history(recent) or None

    command_result = await talk_command_service.maybe_handle_talk_command(
        db=db, org_id=org_id, message=message, actor_role=user.get("role"),
    )
    if command_result.handled:
        await chat_history_service.save_message(
            db, org_id=org_id, user_id=int(user["id"]),
            role=command_result.role, user_message=message,
            ai_response=command_result.response, avatar_mode=write_mode,
        )
        await conversation_learning_service.learn_from_message(
            db=db, org_id=org_id, actor_user_id=int(user["id"]), message=message,
        )
        return JSONResponse(content={
            "role": command_result.role,
            "response": command_result.response,
            "requires_approval": command_result.requires_approval,
            "proposed_actions": [],
        })

    result = await run_agent(
        request=AgentChatRequest(
            message=message,
            force_role="Strategist" if read_mode == "strategy" else (force_role or None),
            avatar_mode=read_mode if read_mode else None,
            provider="openai" if read_mode == "strategy" else None,
        ),
        memory_context=memory_context,
        conversation_history=history,
        organization_id=org_id,
        brain_context=brain_context,
    )

    await chat_history_service.save_message(
        db, org_id=org_id, user_id=int(user["id"]),
        role=result.role, user_message=message,
        ai_response=result.response, avatar_mode=write_mode,
    )
    await conversation_learning_service.learn_from_message(
        db=db, org_id=org_id, actor_user_id=int(user["id"]), message=message,
    )

    return JSONResponse(content={
        "role": result.role,
        "response": result.response,
        "requires_approval": result.requires_approval,
        "proposed_actions": [a.model_dump() for a in result.proposed_actions],
        "confidence_score": result.confidence_score,
        "confidence_level": result.confidence_level,
        "needs_human_review": result.needs_human_review,
        "policy_score": result.policy_score,
        "blocked_by_policy": result.blocked_by_policy,
    })


@router.get("/web/chat/history", include_in_schema=False)
async def web_chat_history(
    avatar_mode: str | None = None,
    user: dict = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Return the last 20 chat turns for the session user's org."""
    from app.services import chat_history as chat_history_service

    org_id = int(user["org_id"])
    resolved_mode = (avatar_mode or str(user.get("default_avatar_mode") or "professional")).strip().lower()
    # Strategy mode bypasses purpose barriers but requires CEO/ADMIN
    if resolved_mode == "strategy" and user["role"] not in {"CEO", "ADMIN"}:
        resolved_mode = "professional"
    avatar_mode = read_avatar_scope(user, resolved_mode)
    recent = await chat_history_service.get_recent(
        db, org_id=org_id, limit=20, avatar_mode=avatar_mode,
    )
    return JSONResponse(content=[
        {
            "id": m.id,
            "role": chat_history_service.decode_role(m.role),
            "user_message": m.user_message,
            "ai_response": m.ai_response,
            "created_at": m.created_at.isoformat(),
        }
        for m in recent
    ])


@router.post("/web/ops/daily-run")
async def web_daily_run(
    draft_email_limit: int = Query(3, ge=0, le=50),
    team: str | None = Query(None, max_length=100),
    _csrf_ok: None = Depends(verify_csrf),
    user: dict = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    from app.api.v1.endpoints.ops import run_daily_run_workflow

    if user["role"] not in {"CEO", "ADMIN", "MANAGER"}:
        raise HTTPException(status_code=403, detail="Insufficient role")
    data = await run_daily_run_workflow(
        db=db,
        org_id=int(user["org_id"]),
        actor_user_id=int(user["id"]),
        draft_email_limit=draft_email_limit,
        team=team,
    )
    return JSONResponse(content=data)


# ── Strategy Workspace Endpoints ────────────────────────────────────────────


@router.post("/web/strategy/push-decision")
async def web_push_decision(
    decision: str = Form(..., max_length=2000),
    _csrf_ok: None = Depends(verify_csrf),
    user: dict = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Push a strategy decision to the business agent's context."""
    from datetime import date as date_cls

    from app.schemas.memory import DailyContextCreate

    if user["role"] not in {"CEO", "ADMIN"}:
        raise HTTPException(status_code=403, detail="Only CEO/ADMIN can push decisions")

    org_id = int(user["org_id"])

    await memory_service.add_daily_context(
        db,
        DailyContextCreate(
            date=date_cls.today(),
            context_type="decision",
            content=f"[STRATEGY DECISION] {decision}",
            related_to="strategy_workspace",
        ),
        organization_id=org_id,
    )

    key = f"strategy.decision.{date_cls.today().isoformat()}.{abs(hash(decision)) % 10000}"
    await memory_service.upsert_profile_memory(
        db, organization_id=org_id,
        key=key, value=decision, category="strategy_decision",
    )

    memory_service.invalidate_memory_cache(org_id)
    return JSONResponse(content={"ok": True, "message": "Decision pushed to business agent."})


@router.post("/web/strategy/rules")
async def web_save_strategy_rule(
    rule_key: str = Form(..., max_length=100),
    rule_value: str = Form(..., max_length=2000),
    _csrf_ok: None = Depends(verify_csrf),
    user: dict = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Save or update a strategy rule."""
    if user["role"] not in {"CEO", "ADMIN"}:
        raise HTTPException(status_code=403, detail="Only CEO/ADMIN can set strategy rules")

    org_id = int(user["org_id"])
    entry = await memory_service.upsert_avatar_memory(
        db, organization_id=org_id,
        avatar_mode="strategy",
        key=f"rule.{rule_key}",
        value=rule_value,
    )
    return JSONResponse(content={"ok": True, "id": entry.id, "key": entry.key})
