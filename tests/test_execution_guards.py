"""Unit tests for execution_engine guard logic and handler helpers.

These cover code paths that the E2E tests in test_execution_engine.py do NOT exercise:
  - cross-org execution denied
  - non-approved status rejected
  - already-executed approval skipped
  - unknown handler type → skipped
  - email send_message path routing (reply vs compose)
  - _run_handler type validation
  - handler timeout
"""
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.execution_engine import (
    HANDLERS,
    _run_handler,
    execute_approval,
)


def _fake_approval(
    *,
    id: int = 1,
    organization_id: int = 1,
    approval_type: str = "assign_leads",
    status: str = "approved",
    executed_at=None,
    payload_json: dict | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=id,
        organization_id=organization_id,
        approval_type=approval_type,
        status=status,
        executed_at=executed_at,
        payload_json=payload_json or {},
    )


@pytest.mark.asyncio
async def test_cross_org_execution_denied():
    db = AsyncMock()
    approval = _fake_approval(organization_id=2)
    with pytest.raises(ValueError, match="Cross-org execution denied"):
        await execute_approval(db, approval, actor_user_id=1, actor_org_id=1)


@pytest.mark.asyncio
async def test_non_approved_status_rejected():
    db = AsyncMock()
    for bad_status in ("pending", "rejected"):
        approval = _fake_approval(status=bad_status)
        with pytest.raises(ValueError, match="Cannot execute approval"):
            await execute_approval(db, approval, actor_user_id=1, actor_org_id=1)


@pytest.mark.asyncio
async def test_already_executed_skipped():
    db = AsyncMock()
    approval = _fake_approval(executed_at=datetime.now(UTC))
    # Should return without raising or doing anything
    result = await execute_approval(db, approval, actor_user_id=1, actor_org_id=1)
    assert result is None
    # No execution_service calls should be made
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_unknown_handler_type_skipped():
    db = AsyncMock()
    approval = _fake_approval(approval_type="nonexistent_handler_xyz")
    fake_execution = SimpleNamespace(id=99)

    with (
        patch("app.services.execution_engine.execution_service") as mock_exec,
        patch("app.services.execution_engine.record_action", new_callable=AsyncMock),
        patch("app.services.execution_engine._finalize_execution", new_callable=AsyncMock) as mock_finalize,
    ):
        mock_exec.create_execution = AsyncMock(return_value=(fake_execution, True))
        await execute_approval(db, approval, actor_user_id=1, actor_org_id=1)

    mock_finalize.assert_awaited_once()
    call_kwargs = mock_finalize.call_args
    assert call_kwargs[1]["status"] == "skipped"
    assert call_kwargs[1]["output"] == {"reason": "no_handler"}


@pytest.mark.asyncio
async def test_send_message_reply_path():
    """Email path routes to send_approved_reply when email_id is present."""
    db = AsyncMock()
    approval = _fake_approval(
        approval_type="send_message",
        payload_json={"email_id": 42},
    )
    fake_execution = SimpleNamespace(id=99)

    with (
        patch("app.services.execution_engine.execution_service") as mock_exec,
        patch("app.services.execution_engine.record_action", new_callable=AsyncMock),
        patch("app.services.execution_engine.send_approved_reply", new_callable=AsyncMock, return_value=True) as mock_reply,
        patch("app.services.execution_engine.send_approved_compose", new_callable=AsyncMock) as mock_compose,
        patch("app.services.execution_engine._finalize_execution", new_callable=AsyncMock) as mock_finalize,
    ):
        mock_exec.create_execution = AsyncMock(return_value=(fake_execution, True))
        await execute_approval(db, approval, actor_user_id=1, actor_org_id=1)

    mock_reply.assert_awaited_once()
    mock_compose.assert_not_awaited()
    assert mock_finalize.call_args[1]["status"] == "succeeded"
    assert mock_finalize.call_args[1]["output"]["mode"] == "reply"


@pytest.mark.asyncio
async def test_send_message_compose_path():
    """Email path routes to send_approved_compose when email_id is absent."""
    db = AsyncMock()
    approval = _fake_approval(
        approval_type="send_message",
        payload_json={"to": "someone@example.com", "subject": "Test"},
    )
    fake_execution = SimpleNamespace(id=99)

    with (
        patch("app.services.execution_engine.execution_service") as mock_exec,
        patch("app.services.execution_engine.record_action", new_callable=AsyncMock),
        patch("app.services.execution_engine.send_approved_reply", new_callable=AsyncMock) as mock_reply,
        patch("app.services.execution_engine.send_approved_compose", new_callable=AsyncMock, return_value=True) as mock_compose,
        patch("app.services.execution_engine._finalize_execution", new_callable=AsyncMock) as mock_finalize,
    ):
        mock_exec.create_execution = AsyncMock(return_value=(fake_execution, True))
        await execute_approval(db, approval, actor_user_id=1, actor_org_id=1)

    mock_compose.assert_awaited_once()
    mock_reply.assert_not_awaited()
    assert mock_finalize.call_args[1]["status"] == "succeeded"
    assert mock_finalize.call_args[1]["output"]["mode"] == "compose"


@pytest.mark.asyncio
async def test_run_handler_rejects_non_dict_return():
    """_run_handler raises TypeError if handler returns non-dict."""
    def bad_handler(payload):
        return "not a dict"
    with pytest.raises(TypeError, match="expected dict"):
        await _run_handler(bad_handler, {})


@pytest.mark.asyncio
async def test_run_handler_works_with_async_handler():
    async def async_handler(payload):
        return {"ok": True, "count": payload.get("n", 0)}

    result = await _run_handler(async_handler, {"n": 5})
    assert result == {"ok": True, "count": 5}


@pytest.mark.asyncio
async def test_run_handler_works_with_sync_handler():
    def sync_handler(payload):
        return {"ok": True}

    result = await _run_handler(sync_handler, {})
    assert result == {"ok": True}


def test_handlers_registry_has_expected_keys():
    expected = {
        "assign_leads", "spend", "spend_money", "fetch_calendar_digest",
        "assign_task", "change_crm_status", "send_email", "send_slack",
        "create_task", "ai_generate", "http_request", "wait", "noop",
    }
    assert expected == set(HANDLERS.keys())


def test_handler_assign_leads():
    result = HANDLERS["assign_leads"]({"count": 10})
    assert result == {"action": "assign_leads", "assigned_count": 10}


def test_handler_spend_rejects_negative():
    with pytest.raises(ValueError, match="greater than zero"):
        HANDLERS["spend"]({"amount": -1})


def test_handler_spend_success():
    result = HANDLERS["spend"]({"amount": 50.0})
    assert result == {"action": "spend", "approved_amount": 50.0}
