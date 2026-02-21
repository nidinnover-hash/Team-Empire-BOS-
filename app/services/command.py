from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.command import Command
from app.schemas.command import CommandCreate

# These are placeholder keys — skip the OpenAI call for them
_PLACEHOLDER_KEYS = {"sk-your-key-here", "sk-xxxxxxxxxxxxxxxxxxxxxxxx", ""}


async def _call_openai(text: str) -> tuple[str | None, str | None]:
    """
    Call GPT-4o-mini and return (response_text, model_name).
    Returns (None, None) when no real key is set or on any error.
    """
    key = settings.OPENAI_API_KEY
    if not key or key in _PLACEHOLDER_KEYS:
        return None, None
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=key)
        result = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a Personal Clone — Nidin's sharp, efficient AI assistant. "
                        "Be concise, practical, and direct. Help manage business, "
                        "personal life, and long-term goals."
                    ),
                },
                {"role": "user", "content": text},
            ],
            max_tokens=600,
            timeout=15.0,
        )
        return result.choices[0].message.content, "gpt-4o-mini"
    except Exception:
        return None, None


async def create_command(db: AsyncSession, data: CommandCreate) -> Command:
    ai_response = data.ai_response
    model_used = None

    # Auto-call OpenAI only when no manual response was provided
    if ai_response is None:
        ai_response, model_used = await _call_openai(data.command_text)

    command = Command(
        command_text=data.command_text,
        ai_response=ai_response,
        model_used=model_used,
    )
    db.add(command)
    await db.commit()
    await db.refresh(command)
    return command


async def list_commands(db: AsyncSession, limit: int = 50) -> list[Command]:
    result = await db.execute(
        select(Command).order_by(Command.created_at.desc()).limit(limit)
    )
    return list(result.scalars().all())
