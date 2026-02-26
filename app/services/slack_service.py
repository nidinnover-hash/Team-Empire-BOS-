"""
Slack Sync Service — read recent channel messages and inject them into AI context.

Stores the Bot Token in Integration.config_json["access_token"] so it is
automatically Fernet-encrypted/decrypted by token_crypto.

Sync stores a compressed per-channel message digest in DailyContext
(context_type="slack", related_to=channel_name) — it does NOT persist every
individual Slack message, which would be too noisy for the task list.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.resilience import run_with_retry
from app.core.tenant import require_org_id
from app.models.memory import DailyContext
from app.schemas.memory import DailyContextCreate
from app.services import integration as integration_service
from app.services import memory as memory_service
from app.tools.slack import (
    auth_test,
    get_channel_history,
    get_user_name,
    list_channels,
    post_message,
)

logger = logging.getLogger(__name__)

_SLACK_TYPE = "slack"
_MAX_CHANNELS = 10     # read at most N channels per sync
_MSGS_PER_CHANNEL = 20  # last N messages per channel
_MAX_MSG_CHARS = 120    # truncate each message preview


async def get_slack_status(db: AsyncSession, org_id: int) -> dict[str, Any]:
    item = await integration_service.get_integration_by_type(db, org_id, _SLACK_TYPE)
    if item is None:
        return {"connected": False, "last_sync_at": None, "team": None, "channels_tracked": None}
    cfg = item.config_json or {}
    return {
        "connected": item.status == "connected",
        "last_sync_at": item.last_sync_at.isoformat() if item.last_sync_at else None,
        "team": cfg.get("team"),
        "channels_tracked": cfg.get("channels_tracked"),
    }


async def connect_slack(
    db: AsyncSession, org_id: int, bot_token: str
) -> dict[str, Any]:
    """
    Verify the Slack bot token and store it encrypted in the Integration table.
    Raises on auth failure.
    """
    require_org_id(org_id)
    info = await run_with_retry(lambda: auth_test(bot_token))

    config_json = {
        "access_token": bot_token,  # encrypt_config() auto-encrypts this field
        "team": info.get("team"),
        "team_id": info.get("team_id"),
        "bot_user_id": info.get("user_id"),
        "channels_tracked": 0,
        "connected_at": datetime.now(UTC).isoformat(),
    }

    item = await integration_service.connect_integration(
        db,
        organization_id=org_id,
        integration_type=_SLACK_TYPE,
        config_json=config_json,
    )
    return {
        "id": item.id,
        "status": item.status,
        "team": config_json["team"],
    }


async def sync_slack_messages(db: AsyncSession, org_id: int) -> dict[str, Any]:
    """
    Read recent messages from all joined channels and store digests in DailyContext.

    Returns {"channels_synced": N, "messages_read": M, "error": None}.
    """
    item = await integration_service.get_integration_by_type(db, org_id, _SLACK_TYPE)
    if item is None or item.status != "connected":
        return {"channels_synced": 0, "messages_read": 0, "error": "Slack integration is not connected"}

    cfg = item.config_json or {}
    token = cfg.get("access_token")
    if not token:
        return {"channels_synced": 0, "messages_read": 0, "error": "Missing access_token in Slack config"}

    channels_synced = 0
    messages_read = 0
    today = date.today()
    user_name_cache: dict[str, str] = {}  # cache user_id → display_name within this sync

    try:
        channels = await run_with_retry(lambda: list_channels(token))
        channels = channels[:_MAX_CHANNELS]

        for channel in channels:
            channel_id = channel.get("id", "")
            channel_name = channel.get("name", channel_id)
            if not channel_id:
                continue

            async def _load_channel_history(cid: str = channel_id) -> list[dict[str, Any]]:
                return await get_channel_history(token, cid, limit=_MSGS_PER_CHANNEL)

            messages = await run_with_retry(_load_channel_history)
            if not messages:
                continue

            # Build a compact digest of recent human messages
            lines: list[str] = []
            for msg in messages:
                user_id = msg.get("user", "")
                text = (msg.get("text") or "").replace("\n", " ").strip()
                if not text:
                    continue
                if user_id:
                    if user_id not in user_name_cache:
                        async def _load_user_name(uid: str = user_id) -> str:
                            return await get_user_name(token, uid)

                        user_name_cache[user_id] = await run_with_retry(_load_user_name)
                    display_name = user_name_cache[user_id]
                else:
                    display_name = "unknown"
                preview = text[:_MAX_MSG_CHARS] + ("…" if len(text) > _MAX_MSG_CHARS else "")
                lines.append(f"@{display_name}: {preview}")
                messages_read += 1

            if lines:
                digest = "\n".join(lines[:15])  # cap at 15 lines per channel
                new_content = f"#{channel_name} recent activity:\n{digest}"
                related_key = f"#{channel_name}"
                # Dedup: update existing context for this channel+date, or insert new
                existing_ctx = await db.execute(
                    select(DailyContext).where(
                        DailyContext.organization_id == org_id,
                        DailyContext.date == today,
                        DailyContext.context_type == "slack",
                        DailyContext.related_to == related_key,
                    )
                )
                row = existing_ctx.scalar_one_or_none()
                if row:
                    row.content = new_content
                    await db.commit()
                else:
                    await memory_service.add_daily_context(
                        db=db,
                        organization_id=org_id,
                        data=DailyContextCreate(
                            date=today,
                            context_type="slack",
                            content=new_content,
                            related_to=related_key,
                        ),
                    )
                channels_synced += 1

    except (httpx.HTTPError, RuntimeError, ValueError, TypeError, TimeoutError) as exc:
        logger.warning("Slack sync failed: %s", type(exc).__name__)
        return {"channels_synced": channels_synced, "messages_read": messages_read, "error": type(exc).__name__}
    finally:
        # Always update last_sync_at so the scheduler doesn't retry immediately on failure
        try:
            cfg["channels_tracked"] = channels_synced
            item.config_json = cfg
            await integration_service.mark_sync_time(db, item)
        except (RuntimeError, ValueError, TypeError):
            logger.debug("Failed to update Slack sync timestamp", exc_info=True)

    return {"channels_synced": channels_synced, "messages_read": messages_read, "error": None}


async def send_to_slack(
    db: AsyncSession, org_id: int, channel_id: str, text: str
) -> dict[str, Any]:
    """
    Send a message to a Slack channel. Used by the execution engine.
    Returns {"ok": True, "ts": "..."} or raises on failure.
    """
    item = await integration_service.get_integration_by_type(db, org_id, _SLACK_TYPE)
    if item is None or item.status != "connected":
        raise ValueError("Slack integration is not connected")

    cfg = item.config_json or {}
    token = cfg.get("access_token")
    if not token:
        raise ValueError("Missing Slack access_token")

    require_org_id(org_id)
    result = await run_with_retry(lambda: post_message(token, channel_id, text))
    return {"ok": True, "ts": result.get("ts")}
