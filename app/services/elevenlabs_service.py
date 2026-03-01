"""ElevenLabs integration service — connect, TTS, voice info."""
from __future__ import annotations

import logging

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.resilience import run_with_retry
from app.services.integration import (
    connect_integration,
    get_integration_by_type,
    mark_sync_time,
)
from app.tools import elevenlabs as elevenlabs_tool

logger = logging.getLogger(__name__)
_TYPE = "elevenlabs"


async def connect_elevenlabs(
    db: AsyncSession, org_id: int, api_key: str
) -> dict:
    await run_with_retry(lambda: elevenlabs_tool.get_user_info(api_key))
    integration = await connect_integration(
        db, organization_id=org_id, integration_type=_TYPE,
        config_json={"api_key": api_key},
    )
    return {"id": integration.id, "connected": True}


async def get_elevenlabs_status(db: AsyncSession, org_id: int) -> dict:
    integration = await get_integration_by_type(db, org_id, _TYPE)
    if not integration or integration.status != "connected":
        return {"connected": False, "voices_available": 0, "characters_used": 0, "character_limit": 0}
    api_key = (integration.config_json or {}).get("api_key", "")
    voices_count = 0
    chars_used = 0
    chars_limit = 0
    try:
        voices = await run_with_retry(lambda: elevenlabs_tool.list_voices(api_key))
        voices_count = len(voices)
        usage = await run_with_retry(lambda: elevenlabs_tool.get_usage(api_key))
        chars_used = usage.get("character_count", 0)
        chars_limit = usage.get("character_limit", 0)
    except (httpx.HTTPError, RuntimeError, ValueError, TypeError, TimeoutError) as exc:
        logger.warning("ElevenLabs status check degraded for org %s: %s", org_id, type(exc).__name__)
    return {
        "connected": True,
        "last_sync_at": integration.last_sync_at.isoformat() if integration.last_sync_at else None,
        "voices_available": voices_count,
        "characters_used": chars_used,
        "character_limit": chars_limit,
    }


async def text_to_speech(
    db: AsyncSession, org_id: int, text: str, voice_id: str | None = None
) -> dict:
    integration = await get_integration_by_type(db, org_id, _TYPE)
    if not integration or integration.status != "connected":
        raise ValueError("ElevenLabs not connected")
    api_key = (integration.config_json or {}).get("api_key", "")
    vid = voice_id or settings.ELEVENLABS_DEFAULT_VOICE_ID
    audio_bytes = await run_with_retry(lambda: elevenlabs_tool.text_to_speech(
        api_key, voice_id=vid, text=text,
    ))
    await mark_sync_time(db, integration)
    return {
        "audio_size_bytes": len(audio_bytes),
        "voice_id": vid,
        "model": "eleven_multilingual_v2",
        "audio": audio_bytes,
    }
