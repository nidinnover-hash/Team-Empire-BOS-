"""
Persistent AI chat history — save and retrieve conversation turns.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat_message import ChatMessage


async def save_message(
    db: AsyncSession,
    org_id: int,
    user_id: int | None,
    role: str,
    user_message: str,
    ai_response: str,
) -> ChatMessage:
    msg = ChatMessage(
        organization_id=org_id,
        user_id=user_id,
        role=role,
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
) -> list[ChatMessage]:
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.organization_id == org_id)
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
