from datetime import date, timedelta
from urllib.parse import urlencode

import httpx

GOOGLE_AUTH_BASE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_CALENDAR_EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events"
GOOGLE_CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.readonly"

_TIMEOUT = 20.0

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=_TIMEOUT)
    return _client


def build_google_auth_url(
    client_id: str,
    redirect_uri: str,
    state: str,
) -> str:
    query = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": GOOGLE_CALENDAR_SCOPE,
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
    )
    return f"{GOOGLE_AUTH_BASE_URL}?{query}"


async def exchange_code_for_tokens(
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
) -> dict:
    c = _get_client()
    response = await c.post(
        GOOGLE_TOKEN_URL,
        data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
    )
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, dict) else {}


async def refresh_access_token(
    refresh_token: str,
    client_id: str,
    client_secret: str,
) -> dict:
    c = _get_client()
    response = await c.post(
        GOOGLE_TOKEN_URL,
        data={
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
        },
    )
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, dict) else {}


async def list_events_for_day(
    access_token: str,
    day: date,
    calendar_id: str = "primary",
) -> list[dict]:
    time_min = f"{day.isoformat()}T00:00:00Z"
    next_day = day + timedelta(days=1)
    time_max = f"{next_day.isoformat()}T00:00:00Z"
    url = GOOGLE_CALENDAR_EVENTS_URL.format(calendar_id=calendar_id)
    c = _get_client()
    response = await c.get(
        url,
        params={
            "singleEvents": "true",
            "orderBy": "startTime",
            "timeMin": time_min,
            "timeMax": time_max,
        },
        headers={"Authorization": f"Bearer {access_token}"},
    )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        return []
    items = data.get("items", [])
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []
