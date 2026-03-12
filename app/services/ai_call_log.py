"""AI call observability — persist AI provider call metrics (latency, tokens, errors)."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy.exc import SQLAlchemyError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def log_ai_call(
    db: AsyncSession | None,
    *,
    organization_id: int,
    provider: str,
    model_name: str,
    latency_ms: int,
    request_id: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    used_fallback: bool = False,
    fallback_from: str | None = None,
    error_type: str | None = None,
    prompt_type: str | None = None,
) -> None:
    """Persist one AI call log entry. Best-effort; failures are logged and not raised."""
    try:
        from app.models.ai_call_log import AiCallLog

        log_entry = AiCallLog(
            organization_id=organization_id,
            provider=provider,
            model_name=model_name,
            request_id=request_id,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            used_fallback=used_fallback,
            fallback_from=fallback_from,
            error_type=error_type,
            prompt_type=prompt_type,
        )
        if db is not None:
            db.add(log_entry)
            await db.flush()
        else:
            from app.db.session import AsyncSessionLocal

            async with AsyncSessionLocal() as session:
                session.add(log_entry)
                await session.commit()
    except (
        SQLAlchemyError,
        RuntimeError,
        TimeoutError,
        OSError,
        ValueError,
        TypeError,
        AttributeError,
    ) as exc:
        logger.warning(
            "Failed to persist AI call log: %s",
            type(exc).__name__,
            exc_info=True,
        )
