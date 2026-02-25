"""ElevenLabs API — text-to-speech and voice cloning.

Pure async httpx client, no DB.
"""
from __future__ import annotations

from typing import Any

import httpx

_BASE = "https://api.elevenlabs.io/v1"
_TIMEOUT = 30.0


def _headers(api_key: str) -> dict[str, str]:
    return {"xi-api-key": api_key}


async def list_voices(api_key: str) -> list[dict[str, Any]]:
    """List all available voices."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(f"{_BASE}/voices", headers=_headers(api_key))
        resp.raise_for_status()
        body = resp.json()
        voices = body.get("voices", [])
        return voices if isinstance(voices, list) else []


async def text_to_speech(
    api_key: str,
    *,
    voice_id: str,
    text: str,
    model_id: str = "eleven_multilingual_v2",
    stability: float = 0.5,
    similarity_boost: float = 0.75,
) -> bytes:
    """Convert text to speech audio (returns MP3 bytes)."""
    payload = {
        "text": text,
        "model_id": model_id,
        "voice_settings": {
            "stability": stability,
            "similarity_boost": similarity_boost,
        },
    }
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            f"{_BASE}/text-to-speech/{voice_id}",
            json=payload,
            headers={**_headers(api_key), "Content-Type": "application/json"},
        )
        resp.raise_for_status()
        return resp.content


async def get_voice(api_key: str, voice_id: str) -> dict[str, Any]:
    """Get voice details."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(f"{_BASE}/voices/{voice_id}", headers=_headers(api_key))
        resp.raise_for_status()
        body = resp.json()
        return body if isinstance(body, dict) else {}


async def get_user_info(api_key: str) -> dict[str, Any]:
    """Get user subscription info (verifies key)."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(f"{_BASE}/user", headers=_headers(api_key))
        resp.raise_for_status()
        body = resp.json()
        return body if isinstance(body, dict) else {}


async def get_usage(api_key: str) -> dict[str, Any]:
    """Get character usage stats."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(f"{_BASE}/user/subscription", headers=_headers(api_key))
        resp.raise_for_status()
        body = resp.json()
        return body if isinstance(body, dict) else {}
