from datetime import datetime, timezone
from types import SimpleNamespace

from sqlalchemy import select

from app.core.deps import get_db
from app.main import app as fastapi_app
from app.models.approval import Approval
from app.models.execution import Execution
from app.services import email_service, execution_engine


async def _db_session():
    override = fastapi_app.dependency_overrides[get_db]
    agen = override()
    session = await agen.__anext__()
    return session, agen


async def test_execute_send_message_compose_payload_succeeds(client, monkeypatch):
    db, agen = await _db_session()
    try:
        approval = Approval(
            organization_id=1,
            requested_by=1,
            approval_type="send_message",
            payload_json={
                "compose": True,
                "to": "client@example.com",
                "subject": "Proposal update",
                "draft_body": "Hi, sharing the latest update.",
            },
            status="approved",
            approved_by=1,
            approved_at=datetime.now(timezone.utc),
        )
        db.add(approval)
        await db.commit()
        await db.refresh(approval)

        async def fake_get_integration_by_type(*_args, **_kwargs):
            return SimpleNamespace(config_json={"access_token": "a", "refresh_token": "r"})

        send_calls = {"count": 0}

        def fake_send_email(**_kwargs):
            send_calls["count"] += 1
            return True

        monkeypatch.setattr(email_service, "get_integration_by_type", fake_get_integration_by_type)
        monkeypatch.setattr(email_service.gmail_tool, "send_email", fake_send_email)

        await execution_engine.execute_approval(db=db, approval=approval, actor_user_id=1, actor_org_id=1)
        await db.refresh(approval)
        assert approval.executed_at is not None
        assert send_calls["count"] == 1

        row = await db.execute(
            select(Execution).where(
                Execution.approval_id == approval.id,
                Execution.organization_id == 1,
            )
        )
        execution = row.scalar_one()
        assert execution.status == "succeeded"
        assert execution.output_json.get("action") == "send_message"
        assert execution.output_json.get("mode") == "compose"
        assert execution.output_json.get("sent") is True
    finally:
        await agen.aclose()


async def test_execute_send_message_compose_payload_missing_body_fails(client, monkeypatch):
    db, agen = await _db_session()
    try:
        approval = Approval(
            organization_id=1,
            requested_by=1,
            approval_type="send_message",
            payload_json={
                "compose": True,
                "to": "client@example.com",
                "subject": "Proposal update",
            },
            status="approved",
            approved_by=1,
            approved_at=datetime.now(timezone.utc),
        )
        db.add(approval)
        await db.commit()
        await db.refresh(approval)

        async def fake_get_integration_by_type(*_args, **_kwargs):
            return SimpleNamespace(config_json={"access_token": "a", "refresh_token": "r"})

        send_calls = {"count": 0}

        def fake_send_email(**_kwargs):
            send_calls["count"] += 1
            return True

        monkeypatch.setattr(email_service, "get_integration_by_type", fake_get_integration_by_type)
        monkeypatch.setattr(email_service.gmail_tool, "send_email", fake_send_email)

        await execution_engine.execute_approval(db=db, approval=approval, actor_user_id=1, actor_org_id=1)
        await db.refresh(approval)
        assert approval.executed_at is None
        assert send_calls["count"] == 0

        row = await db.execute(
            select(Execution).where(
                Execution.approval_id == approval.id,
                Execution.organization_id == 1,
            )
        )
        execution = row.scalar_one()
        assert execution.status == "failed"
        assert execution.output_json.get("mode") == "compose"
        assert execution.output_json.get("sent") is False
    finally:
        await agen.aclose()
