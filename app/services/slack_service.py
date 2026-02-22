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
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import integration as integration_service
from app.services import memory as memory_service
from app.schemas.memory import DailyContextCreate
from app.tools.slack import auth_test, get_channel_history, get_user_name, list_channels, post_message

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
    info = await auth_test(bot_token)

    config_json = {
        "access_token": bot_token,  # encrypt_config() auto-encrypts this field
        "team": info.get("team"),
        "team_id": info.get("team_id"),
        "bot_user_id": info.get("user_id"),
        "channels_tracked": 0,
        "connected_at": datetime.now(timezone.utc).isoformat(),
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

    try:
        channels = await list_channels(token)
        channels = channels[:_MAX_CHANNELS]

        for channel in channels:
            channel_id = channel.get("id", "")
            channel_name = channel.get("name", channel_id)
            if not channel_id:
                continue

            messages = await get_channel_history(token, channel_id, limit=_MSGS_PER_CHANNEL)
            if not messages:
                continue

            # Build a compact digest of recent human messages
            lines: list[str] = []
            for msg in messages:
                user_id = msg.get("user", "")
                text = (msg.get("text") or "").replace("\n", " ").strip()
                if not text:
                    continue
                display_name = await get_user_name(token, user_id) if user_id else "unknown"
                preview = text[:_MAX_MSG_CHARS] + ("…" if len(text) > _MAX_MSG_CHARS else "")
                lines.append(f"@{display_name}: {preview}")
                messages_read += 1

            if lines:
                digest = "\n".join(lines[:15])  # cap at 15 lines per channel
                await memory_service.add_daily_context(
                    db=db,
                    organization_id=org_id,
                    data=DailyContextCreate(
                        date=today,
                        context_type="slack",
                        content=f"#{channel_name} recent activity:\n{digest}",
                        related_to=f"#{channel_name}",
                    ),
                )
                channels_synced += 1

    except Exception as exc:
        logger.warning("Slack sync failed: %s", type(exc).__name__)
        return {"channels_synced": channels_synced, "messages_read": messages_read, "error": type(exc).__name__}

    # Update channels_tracked in config
    cfg["channels_tracked"] = channels_synced
    item.config_json = cfg
    await integration_service.mark_sync_time(db, item)
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

    result = await post_message(token, channel_id, text)
    return {"ok": True, "ts": result.get("ts")}
