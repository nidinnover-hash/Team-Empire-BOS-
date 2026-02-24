from datetime import datetime, timezone
from unittest.mock import AsyncMock

from app.core.deps import get_db
from app.main import app as fastapi_app
from app.models.email import Email
from typing import cast


async def _insert_email(
    *,
    org_id: int,
    gmail_id: str,
    subject: str,
    body: str,
    from_address: str = "manager@empireoe.com",
) -> int:
    override = fastapi_app.dependency_overrides[get_db]
    agen = override()
    session = await agen.__anext__()
    try:
        row = Email(
            organization_id=org_id,
            gmail_id=gmail_id,
            subject=subject,
            body_text=body,
            from_address=from_address,
            received_at=datetime.now(timezone.utc),
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return cast(int, row.id)
    finally:
        await agen.aclose()


async def test_report_template_endpoint(client):
    resp = await client.get("/api/v1/email/control/report-template")
    assert resp.status_code == 200
    body = resp.json()
    assert "subject_prefix" in body
    assert "required_fields" in body


async def test_control_process_creates_task_for_action_email(client):
    await _insert_email(
        org_id=1,
        gmail_id="email-action-1",
        subject="Action required: update sprint board",
        body="Please follow up and send next steps before deadline.",
    )
    resp = await client.post("/api/v1/email/control/process?limit=20")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["tasks_created"] >= 1
    assert any(item["classification"] in {"action", "escalation"} for item in payload["items"])


async def test_control_process_creates_approval_for_approval_email(client, monkeypatch):
    monkeypatch.setattr("app.services.email_service.call_ai", AsyncMock(return_value="Approved draft content"))
    monkeypatch.setattr("app.tools.gmail.create_draft", lambda **_kwargs: "draft_123")

    email_id = await _insert_email(
        org_id=1,
        gmail_id="email-approval-1",
        subject="Need approval for vendor payout",
        body="Please approve this request today.",
    )
    resp = await client.post("/api/v1/email/control/process?limit=20")
    assert resp.status_code == 200
    payload = resp.json()
    matched = [item for item in payload["items"] if item["email_id"] == email_id]
    assert matched
    assert matched[0]["classification"] == "approval"
    assert payload["approvals_created"] >= 1


async def test_pending_digest_endpoints(client):
    get_resp = await client.get("/api/v1/email/control/pending-digest")
    assert get_resp.status_code == 200
    digest = get_resp.json()
    assert "lines" in digest

    draft_resp = await client.post("/api/v1/email/control/pending-digest/draft")
    assert draft_resp.status_code == 200
    body = draft_resp.json()
    assert body["ok"] is True
    assert body["approval_id"] > 0
