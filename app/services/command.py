import logging
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.command import Command
from app.schemas.command import CommandCreate

logger = logging.getLogger(__name__)

_UNUSUAL_ACTIVITY_TOKENS = (
    "delete",
    "shutdown",
    "fire",
    "wire transfer",
    "drop table",
    "kill server",
    "production deploy",
    "reset",
)


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _is_unusual_activity(text: str) -> bool:
    lowered = _normalize_text(text)
    return any(token in lowered for token in _UNUSUAL_ACTIVITY_TOKENS)


def _text_prefix(text: str) -> str:
    words = [w for w in re.findall(r"[a-zA-Z0-9]+", _normalize_text(text)) if len(w) >= 3]
    return " ".join(words[:4])


async def _pattern_hint(db: AsyncSession, organization_id: int, command_text: str) -> str | None:
    prefix = _text_prefix(command_text)
    if not prefix:
        return None
    result = await db.execute(
        select(Command.command_text)
        .where(Command.organization_id == organization_id)
        .order_by(Command.created_at.desc(), Command.id.desc())
        .limit(min(500, max(10, int(settings.CLONE_PATTERN_WINDOW))))
    )
    prior = [str(row[0]) for row in result.all()]
    if not prior:
        return None
    hits = 0
    for text in prior:
        normalized = _normalize_text(text)
        if prefix in normalized:
            hits += 1
    if hits < 3:
        return None
    return (
        f"Pattern detected ({hits} similar commands). Draft policy: "
        f"'{prefix}' workflow can be standardized with manual approval first, "
        "then partial automation after 2 successful cycles."
    )


async def _call_ai(
    text: str,
    organization_id: int,
    require_clarification: bool,
) -> tuple[str | None, str | None]:
    """
    Route through the central AI router (supports all providers + fallback).
    Returns (response_text, model_name).
    """
    from app.services.ai_router import _get_model, call_ai

    if not settings.FEATURE_AI_COMMANDS:
        return None, None

    try:
        behavior_clause = (
            "Always ask one clarifying question before giving final actions."
            if require_clarification
            else "Give concise execution guidance."
        )
        response = await call_ai(
            system_prompt=(
                "You are Nidin BOS - Nidin's sharp, efficient AI assistant. "
                "Be concise, practical, and direct. "
                f"{behavior_clause} "
                "Study recurring patterns, suggest policy drafts, "
                "and keep automation in suggest-only mode until user approval."
            ),
            user_message=text,
            max_tokens=600,
            organization_id=organization_id,
        )
        if response and not response.startswith("Error:"):
            provider = settings.DEFAULT_AI_PROVIDER
            return response, _get_model(provider)
        return None, None
    except (TimeoutError, ConnectionError, ValueError) as exc:
        logger.warning("AI call failed for command text: %s", type(exc).__name__)
        return None, None


async def create_command(
    db: AsyncSession, data: CommandCreate, organization_id: int
) -> Command:
    ai_response = data.ai_response
    model_used = None
    unusual = bool(settings.CLONE_UNUSUAL_ACTIVITY_ALERTS and _is_unusual_activity(data.command_text))
    require_clarification = bool(settings.CLONE_REQUIRE_CLARIFYING_QUESTION)

    # Auto-call AI only when no manual response was provided
    if ai_response is None:
        ai_response, model_used = await _call_ai(
            data.command_text,
            organization_id,
            require_clarification=require_clarification,
        )
        pattern_note = await _pattern_hint(db, organization_id, data.command_text)
        additions: list[str] = []
        if pattern_note:
            additions.append(pattern_note)
        if unusual:
            additions.append(
                "Unusual activity risk detected. Keep this in manual approval mode and verify intent, scope, and rollback."
            )
        if additions:
            base = ai_response or ""
            ai_response = (base + "\n\n" + "\n".join(f"- {x}" for x in additions)).strip()

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
    db: AsyncSession, organization_id: int, limit: int = 50
) -> list[Command]:
    result = await db.execute(
        select(Command)
        .where(Command.organization_id == organization_id)
        .order_by(Command.created_at.desc(), Command.id.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
