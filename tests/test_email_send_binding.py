from datetime import UTC, datetime
from types import SimpleNamespace

from sqlalchemy import select

from app.core.deps import get_db
from app.main import app as fastapi_app
from app.models.approval import Approval
from app.models.email import Email
from app.models.event import Event
from app.services import email_service


async def _db_session():
    override = fastapi_app.dependency_overrides[get_db]
    agen = override()
    session = await agen.__anext__()
    return session, agen


async def test_send_rejects_mismatched_approval_payload(client, monkeypatch):
    db, agen = await _db_session()
    try:
        email = Email(
            organization_id=1,
            gmail_id="send-bind-1",
            from_address="lead@example.com",
            subject="Hi",
            body_text="Body",
            draft_reply="Draft reply text",
            created_at=datetime.now(UTC),
        )
        db.add(email)
        await db.commit()
        await db.refresh(email)

        approval = Approval(
            organization_id=1,
            requested_by=1,
            approval_type="send_message",
            payload_json={"email_id": email.id + 999},
            status="approved",
            approved_by=1,
        )
        db.add(approval)
        await db.commit()
        await db.refresh(approval)

        email.approval_id = approval.id
        await db.commit()

        send_called = {"value": False}

        async def fake_get_integration_by_type(*_args, **_kwargs):
            return SimpleNamespace(config_json={"access_token": "a", "refresh_token": "r"})

        def fake_send_email(**_kwargs):
            send_called["value"] = True
            return True

        monkeypatch.setattr(email_service, "get_integration_by_type", fake_get_integration_by_type)
        monkeypatch.setattr(email_service.gmail_tool, "send_email", fake_send_email)

        sent = await email_service.send_approved_reply(
            db=db,
            email_id=email.id,
            org_id=1,
            actor_user_id=1,
        )
        assert sent is False
        assert send_called["value"] is False
        event_rows = await db.execute(
            select(Event).where(
                Event.organization_id == 1,
                Event.event_type == "email_send_blocked",
                Event.entity_id == email.id,
            )
        )
        events = list(event_rows.scalars().all())
        assert events
        assert events[-1].payload_json.get("reason") == "approval_email_id_mismatch"
    finally:
        await agen.aclose()


async def test_send_uses_linked_approval_once(client, monkeypatch):
    db, agen = await _db_session()
    try:
        email = Email(
            organization_id=1,
            gmail_id="send-bind-2",
            from_address="lead@example.com",
            subject="Hi again",
            body_text="Body",
            draft_reply="Approved draft",
            created_at=datetime.now(UTC),
        )
        db.add(email)
        await db.commit()
        await db.refresh(email)

        approval = Approval(
            organization_id=1,
            requested_by=1,
            approval_type="send_message",
            payload_json={"email_id": email.id},
            status="approved",
            approved_by=1,
        )
        db.add(approval)
        await db.commit()
        await db.refresh(approval)

        email.approval_id = approval.id
        await db.commit()

        send_calls = {"count": 0}

        async def fake_get_integration_by_type(*_args, **_kwargs):
            return SimpleNamespace(config_json={"access_token": "a", "refresh_token": "r"})

        def fake_send_email(**_kwargs):
            send_calls["count"] += 1
            return True

        monkeypatch.setattr(email_service, "get_integration_by_type", fake_get_integration_by_type)
        monkeypatch.setattr(email_service.gmail_tool, "send_email", fake_send_email)

        first = await email_service.send_approved_reply(
            db=db,
            email_id=email.id,
            org_id=1,
            actor_user_id=1,
        )
        assert first is True
        assert send_calls["count"] == 1

        await db.refresh(email)
        await db.refresh(approval)
        assert email.reply_sent is True
        assert approval.executed_at is not None

        second = await email_service.send_approved_reply(
            db=db,
            email_id=email.id,
            org_id=1,
            actor_user_id=1,
        )
        assert second is False
        assert send_calls["count"] == 1
    finally:
        await agen.aclose()
