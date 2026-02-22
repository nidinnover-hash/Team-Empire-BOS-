from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.schemas.inbox import (
    ConversationAssignRequest,
    ConversationStateUpdateRequest,
    UnifiedConversation,
    UnifiedInboxItem,
)
from app.services import conversation as conversation_service
from app.services import inbox as inbox_service

router = APIRouter(prefix="/inbox", tags=["Inbox"])


def _parse_conversation_id(conversation_id: str) -> tuple[str, str]:
    parts = conversation_id.split(":", 1)
    if len(parts) != 2:
        raise HTTPException(status_code=400, detail="Invalid conversation_id format")
    channel, participant_key = parts[0], parts[1]
    if channel not in {"email", "whatsapp"} or not participant_key:
        raise HTTPException(status_code=400, detail="Invalid conversation_id format")
    return channel, participant_key


@router.get("/unified", response_model=list[UnifiedInboxItem])
async def unified_inbox(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF")),
) -> list[UnifiedInboxItem]:
    return await inbox_service.get_unified_inbox(
        db=db,
        org_id=actor["org_id"],
        limit=limit,
        offset=offset,
    )


@router.get("/conversations", response_model=list[UnifiedConversation])
async def unified_conversations(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF")),
) -> list[UnifiedConversation]:
    return await inbox_service.get_unified_conversations(
        db=db,
        org_id=actor["org_id"],
        limit=limit,
        offset=offset,
    )


@router.patch("/conversations/{conversation_id}/assign", response_model=UnifiedConversation)
async def assign_conversation(
    conversation_id: str,
    data: ConversationAssignRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> UnifiedConversation:
    channel, participant_key = _parse_conversation_id(conversation_id)
    updated = await conversation_service.update_assignment(
        db=db,
        org_id=actor["org_id"],
        channel=channel,
        participant_key=participant_key,
        owner_user_id=data.owner_user_id,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    conversations = await inbox_service.get_unified_conversations(
        db=db,
        org_id=actor["org_id"],
        limit=500,
        offset=0,
    )
    for convo in conversations:
        if convo.conversation_id == conversation_id:
            return convo
    raise HTTPException(status_code=404, detail="Conversation not found")


@router.patch("/conversations/{conversation_id}/state", response_model=UnifiedConversation)
async def update_conversation_state(
    conversation_id: str,
    data: ConversationStateUpdateRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> UnifiedConversation:
    channel, participant_key = _parse_conversation_id(conversation_id)
    updated = await conversation_service.update_state(
        db=db,
        org_id=actor["org_id"],
        channel=channel,
        participant_key=participant_key,
        status=data.status,
        priority=data.priority,
        sla_due_at=data.sla_due_at,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    conversations = await inbox_service.get_unified_conversations(
        db=db,
        org_id=actor["org_id"],
        limit=500,
        offset=0,
    )
    for convo in conversations:
        if convo.conversation_id == conversation_id:
            return convo
    raise HTTPException(status_code=404, detail="Conversation not found")
