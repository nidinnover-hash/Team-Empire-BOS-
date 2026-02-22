from datetime import datetime, timezone
from typing import cast

from app.core.deps import get_db
from app.main import app as fastapi_app
from app.models.email import Email


async def _seed_email_for_org1(gmail_id: str = "unified-email-1") -> int:
    override = fastapi_app.dependency_overrides[get_db]
    agen = override()
    session = await agen.__anext__()
    try:
        email = Email(
            organization_id=1,
            gmail_id=gmail_id,
            thread_id="thread-unified-1",
            from_address="lead@example.com",
            to_address="owner@example.com",
            subject="Need update",
            body_text="Please share the latest status.",
            received_at=datetime.now(timezone.utc),
            is_read=False,
            reply_sent=False,
            created_at=datetime.now(timezone.utc),
        )
        session.add(email)
        await session.commit()
        await session.refresh(email)
        return cast(int, email.id)
    finally:
        await agen.aclose()


async def test_unified_inbox_merges_email_and_whatsapp(client):
    connected = await client.post(
        "/api/v1/integrations/connect",
        json={
            "type": "whatsapp_business",
            "config_json": {
                "access_token": "wa-token",
                "phone_number_id": "1234567890",
            },
        },
    )
    assert connected.status_code == 201

    email_id = await _seed_email_for_org1()
    assert email_id > 0

    webhook = await client.post(
        "/api/v1/integrations/whatsapp/webhook",
        json={
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "metadata": {
                                    "display_phone_number": "+15550001111",
                                    "phone_number_id": "1234567890",
                                },
                                "messages": [
                                    {
                                        "from": "15551234567",
                                        "id": "wamid.TEST123",
                                        "timestamp": str(int(datetime.now(timezone.utc).timestamp())),
                                        "type": "text",
                                        "text": {"body": "Hi there"},
                                    }
                                ],
                            }
                        }
                    ]
                }
            ]
        },
    )
    assert webhook.status_code == 200
    assert webhook.json()["stored"] >= 1

    response = await client.get("/api/v1/inbox/unified?limit=20")
    assert response.status_code == 200
    items = response.json()
    assert any(i["channel"] == "email" for i in items)
    assert any(i["channel"] == "whatsapp" for i in items)
