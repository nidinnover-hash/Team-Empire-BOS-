"""
Persistent AI chat history — save and retrieve conversation turns.
"""
from sqlalchemy import not_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat_message import ChatMessage


def _normalize_avatar_mode(avatar_mode: str | None) -> str:
    mode = (avatar_mode or "professional").strip().lower()
    if mode in {"personal", "entertainment", "strategy"}:
        return mode
    return "professional"


def _encode_role(role: str, avatar_mode: str | None) -> str:
    mode = _normalize_avatar_mode(avatar_mode)
    if ":" in role:
        return role
    return f"{mode}:{role}"


def decode_role(role: str) -> str:
    if ":" not in role:
        return role
    return role.split(":", 1)[1]


async def save_message(
    db: AsyncSession,
    org_id: int,
    user_id: int | None,
    role: str,
    user_message: str,
    ai_response: str,
    avatar_mode: str | None = None,
) -> ChatMessage:
    msg = ChatMessage(
        organization_id=org_id,
        user_id=user_id,
        role=_encode_role(role, avatar_mode),
        user_message=user_message,
        ai_response=ai_response,
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)
    return msg


async def get_recent(
    db: AsyncSession,
    org_id: int,
    limit: int = 20,
    avatar_mode: str | None = None,
) -> list[ChatMessage]:
    role_prefix = f"{_normalize_avatar_mode(avatar_mode)}:%"
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.organization_id == org_id)
        .where(
            or_(
                ChatMessage.role.like(role_prefix),
                not_(ChatMessage.role.like("%:%")),
            )
        )
        .order_by(ChatMessage.created_at.desc())
        .limit(limit)
    )
    messages = list(result.scalars().all())
    messages.reverse()  # oldest first so history reads chronologically
    return messages


def as_openai_history(messages: list[ChatMessage]) -> list[dict]:
    """Convert DB chat turns to OpenAI-format message array."""
    history: list[dict] = []
    for m in messages:
        history.append({"role": "user", "content": m.user_message})
        history.append({"role": "assistant", "content": m.ai_response})
    return history
