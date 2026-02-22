from typing import cast

from datetime import datetime, timezone
from types import SimpleNamespace

from app.core.deps import get_db
from app.core.security import create_access_token
from app.main import app as fastapi_app
from app.models.email import Email


def _auth_headers(user_id: int, email: str, role: str, org_id: int = 1) -> dict:
    token = create_access_token(
        {"id": user_id, "email": email, "role": role, "org_id": org_id}
    )
    return {"Authorization": f"Bearer {token}"}


async def _seed_email_for_org1(gmail_id: str = "draft-flow-gmail-id") -> int:
    override = fastapi_app.dependency_overrides[get_db]
    agen = override()
    session = await agen.__anext__()
    try:
        email = Email(
            organization_id=1,
            gmail_id=gmail_id,
            thread_id="thread-draft-1",
            from_address="lead@example.com",
            to_address="owner@example.com",
            subject="Need fee details",
            body_text="Please share fees and timeline.",
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


async def test_draft_reply_creates_gmail_draft_and_pending_approval(client, monkeypatch):
    from app.services import email_service

    async def fake_call_ai(*_args, **_kwargs) -> str:
        return "Thanks for your message. Here are the fee details."

    async def fake_get_integration_by_type(*_args, **_kwargs):
        return SimpleNamespace(config_json={"access_token": "a", "refresh_token": "r"})

    monkeypatch.setattr(email_service, "call_ai", fake_call_ai)
    monkeypatch.setattr(email_service, "get_integration_by_type", fake_get_integration_by_type)
    monkeypatch.setattr(email_service.gmail_tool, "create_draft", lambda **_kwargs: "gd_123")

    email_id = await _seed_email_for_org1()
    headers = _auth_headers(1, "ceo@org.com", "CEO", 1)

    response = await client.post(
        f"/api/v1/email/{email_id}/draft-reply",
        json={"instruction": "Keep it concise"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "pending_approval"

    inbox = await client.get("/api/v1/email/inbox?limit=20", headers=headers)
    assert inbox.status_code == 200
    items = [row for row in inbox.json() if row["id"] == email_id]
    assert items
    row = items[0]
    assert row["draft_reply"] is not None
    assert row["gmail_draft_id"] == "gd_123"
    assert row["approval_id"] is not None
    assert row["reply_sent"] is False

    approvals = await client.get("/api/v1/approvals?status=pending", headers=headers)
    assert approvals.status_code == 200
    assert any(a["id"] == row["approval_id"] for a in approvals.json())


async def test_draft_reply_never_sends_email(client, monkeypatch):
    from app.services import email_service

    async def fake_call_ai(*_args, **_kwargs) -> str:
        return "Draft only. Do not send."

    async def fake_get_integration_by_type(*_args, **_kwargs):
        return SimpleNamespace(config_json={"access_token": "a", "refresh_token": "r"})

    send_called = {"value": False}

    def fake_send_email(**_kwargs):
        send_called["value"] = True
        return True

    monkeypatch.setattr(email_service, "call_ai", fake_call_ai)
    monkeypatch.setattr(email_service, "get_integration_by_type", fake_get_integration_by_type)
    monkeypatch.setattr(email_service.gmail_tool, "create_draft", lambda **_kwargs: "gd_456")
    monkeypatch.setattr(email_service.gmail_tool, "send_email", fake_send_email)

    email_id = await _seed_email_for_org1(gmail_id="draft-flow-gmail-id-2")
    headers = _auth_headers(1, "ceo@org.com", "CEO", 1)

    response = await client.post(
        f"/api/v1/email/{email_id}/draft-reply",
        json={"instruction": "Professional tone"},
        headers=headers,
    )
    assert response.status_code == 200
    assert send_called["value"] is False
