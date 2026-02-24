from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.core.config import settings

_BASE = "https://api.github.com"
_TIMEOUT = 20.0


def _require_app_config() -> tuple[str, str, str]:
    app_id = (settings.GITHUB_APP_ID or "").strip()
    pem = (settings.GITHUB_PRIVATE_KEY_PEM or "").strip()
    org = (settings.GITHUB_ORG or "").strip()
    if not app_id or not pem or not org:
        raise ValueError("GitHub App config missing: set GITHUB_APP_ID, GITHUB_PRIVATE_KEY_PEM, GITHUB_ORG")
    return app_id, pem.replace("\\n", "\n"), org


def create_app_jwt() -> str:
    import jwt

    app_id, pem, _ = _require_app_config()
    now = datetime.now(timezone.utc)
    payload = {
        "iat": int((now - timedelta(seconds=30)).timestamp()),
        "exp": int((now + timedelta(minutes=9)).timestamp()),
        "iss": app_id,
    }
    return str(jwt.encode(payload, pem, algorithm="RS256"))


def _app_headers(app_jwt: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {app_jwt}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _token_headers(installation_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {installation_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


async def list_app_installations() -> list[dict[str, Any]]:
    app_jwt = create_app_jwt()
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(f"{_BASE}/app/installations", headers=_app_headers(app_jwt))
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list):
            return []
        return [item for item in data if isinstance(item, dict)]


async def create_installation_access_token(installation_id: int) -> dict[str, Any]:
    app_jwt = create_app_jwt()
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            f"{_BASE}/app/installations/{installation_id}/access_tokens",
            headers=_app_headers(app_jwt),
            json={},
        )
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, dict) else {}


async def discover_installation_for_org() -> tuple[str, int]:
    _, _, org = _require_app_config()
    target = org.lower()
    installations = await list_app_installations()
    for item in installations:
        raw_account = item.get("account")
        account = raw_account if isinstance(raw_account, dict) else {}
        login = str(account.get("login", ""))
        if login.lower() == target:
            return login, int(item["id"])
    raise ValueError(f"No GitHub App installation found for org '{org}'")


async def get_installation_token_for_org() -> tuple[str, str, int]:
    login, installation_id = await discover_installation_for_org()
    token_payload = await create_installation_access_token(installation_id)
    token = str(token_payload.get("token") or "")
    if not token:
        raise ValueError("GitHub App installation token missing in response")
    return login, token, installation_id


async def github_get_json(path: str, token: str, *, params: dict[str, Any] | None = None) -> Any:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(f"{_BASE}{path}", headers=_token_headers(token), params=params)
        resp.raise_for_status()
        return resp.json()
