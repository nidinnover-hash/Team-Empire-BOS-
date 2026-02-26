"""
Slack Web API client — async httpx, no DB or settings dependencies.

Authenticates with a Bot Token (xoxb-...).
Token scopes needed: channels:read, channels:history, groups:read, groups:history, chat:write, users:read
"""

from __future__ import annotations

import logging
from typing import Any, cast

import httpx

logger = logging.getLogger(__name__)

_BASE = "https://slack.com/api"
_TIMEOUT = 20.0


def _headers(bot_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {bot_token}",
        "Content-Type": "application/json",
    }


def _raise_if_error(body: dict[str, Any], method: str) -> None:
    """Raise ValueError if Slack returned ok=false."""
    if not body.get("ok"):
        error = body.get("error", "unknown_error")
        raise ValueError(f"Slack {method} failed: {error}")


async def auth_test(bot_token: str) -> dict[str, Any]:
    """Verify the bot token. Returns {ok, team, user, user_id, bot_id, team_id}."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(f"{_BASE}/auth.test", headers=_headers(bot_token))
        resp.raise_for_status()
        body = cast(dict[str, Any], resp.json())
        _raise_if_error(body, "auth.test")
        return body


async def list_channels(
    bot_token: str,
    types: str = "public_channel,private_channel",
    limit: int = 100,
) -> list[dict[str, Any]]:
    """List channels the bot is a member of."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(
            f"{_BASE}/conversations.list",
            headers=_headers(bot_token),
            params={"types": types, "limit": limit, "exclude_archived": "true"},
        )
        resp.raise_for_status()
        body = cast(dict[str, Any], resp.json())
        _raise_if_error(body, "conversations.list")
        channels = body.get("channels") or []
        # Only return channels the bot is in
        return [c for c in channels if isinstance(c, dict) and c.get("is_member")]


async def get_channel_history(
    bot_token: str,
    channel_id: str,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Return recent messages from a channel (newest first)."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(
            f"{_BASE}/conversations.history",
            headers=_headers(bot_token),
            params={"channel": channel_id, "limit": limit},
        )
        resp.raise_for_status()
        body = cast(dict[str, Any], resp.json())
        _raise_if_error(body, "conversations.history")
        messages = body.get("messages") or []
        # Exclude bot messages and system messages
        return [
            m for m in messages
            if isinstance(m, dict)
            and m.get("type") == "message"
            and not m.get("bot_id")
            and m.get("text", "").strip()
        ]


async def post_message(
    bot_token: str,
    channel_id: str,
    text: str,
) -> dict[str, Any]:
    """Post a message to a Slack channel. Returns the posted message object."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            f"{_BASE}/chat.postMessage",
            headers=_headers(bot_token),
            json={"channel": channel_id, "text": text},
        )
        resp.raise_for_status()
        body = cast(dict[str, Any], resp.json())
        _raise_if_error(body, "chat.postMessage")
        return body


async def get_user_name(bot_token: str, user_id: str) -> str:
    """Resolve a Slack user ID to a display name. Returns user_id on failure."""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{_BASE}/users.info",
                headers=_headers(bot_token),
                params={"user": user_id},
            )
            resp.raise_for_status()
            body = cast(dict[str, Any], resp.json())
            if body.get("ok"):
                user = body.get("user", {})
                return user.get("real_name") or user.get("name") or user_id
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        logger.debug("Slack users.info failed for %s: %s", user_id, type(exc).__name__)
    return user_id
