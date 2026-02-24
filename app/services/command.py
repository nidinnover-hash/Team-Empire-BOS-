from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.command import Command
from app.schemas.command import CommandCreate


async def _call_ai(text: str, organization_id: int) -> tuple[str | None, str | None]:
    """
    Route through the central AI router (supports all providers + fallback).
    Returns (response_text, model_name).
    """
    from app.services.ai_router import call_ai, _get_model
    from app.core.config import settings

    if not settings.FEATURE_AI_COMMANDS:
        return None, None

    try:
        response = await call_ai(
            system_prompt=(
                "You are Nidin Nover — Nidin's sharp, efficient AI assistant. "
                "Be concise, practical, and direct. Help manage business, "
                "personal life, and long-term goals."
            ),
            user_message=text,
            max_tokens=600,
            organization_id=organization_id,
        )
        if response and not response.startswith("Error:"):
            provider = settings.DEFAULT_AI_PROVIDER
            return response, _get_model(provider)
        return None, None
    except Exception:
        return None, None


async def create_command(
    db: AsyncSession, data: CommandCreate, organization_id: int = 1
) -> Command:
    ai_response = data.ai_response
    model_used = None

    # Auto-call AI only when no manual response was provided
    if ai_response is None:
        ai_response, model_used = await _call_ai(data.command_text, organization_id)

    command = Command(
        organization_id=organization_id,
        command_text=data.command_text,
        ai_response=ai_response,
        model_used=model_used,
    )
    db.add(command)
    await db.commit()
    await db.refresh(command)
    return command


async def list_commands(
    db: AsyncSession, limit: int = 50, organization_id: int = 1
) -> list[Command]:
    result = await db.execute(
        select(Command)
        .where(Command.organization_id == organization_id)
        .order_by(Command.created_at.desc(), Command.id.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
