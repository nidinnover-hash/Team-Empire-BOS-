from typing import Any, cast

import httpx

GRAPH_API_BASE = "https://graph.facebook.com/v21.0"


def _auth_headers(access_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }


async def get_phone_number_details(access_token: str, phone_number_id: str) -> dict[str, Any]:
    """
    Validate WhatsApp Business credentials by reading phone number metadata.
    """
    url = f"{GRAPH_API_BASE}/{phone_number_id}"
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(
            url,
            params={"fields": "id,display_phone_number,verified_name"},
            headers=_auth_headers(access_token),
        )
        response.raise_for_status()
        return cast(dict[str, Any], response.json())


async def send_text_message(
    access_token: str,
    phone_number_id: str,
    to: str,
    body: str,
) -> dict[str, Any]:
    """
    Send a plain text WhatsApp message via the Meta Cloud API.
    """
    url = f"{GRAPH_API_BASE}/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {"preview_url": False, "body": body},
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(url, json=payload, headers=_auth_headers(access_token))
        response.raise_for_status()
        return cast(dict[str, Any], response.json())
