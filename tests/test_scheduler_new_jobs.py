"""Tests for new scheduler jobs: stale task check, daily briefing notification, contact follow-up."""
from unittest.mock import AsyncMock, patch

import pytest

from app.services.sync_scheduler import (
    _check_follow_up_contacts,
    _check_stale_tasks,
    _maybe_emit_daily_briefing_notification,
)


@pytest.fixture
def mock_db():
    """Simple async mock for db session."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.add = AsyncMock()
    return db


async def test_check_stale_tasks_records_job_run(mock_db):
    """_check_stale_tasks should call _record_job_run even with no tasks."""
    from unittest.mock import MagicMock

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = mock_result

    with patch("app.services.sync_scheduler._record_job_run", new_callable=AsyncMock) as mock_record:
        await _check_stale_tasks(mock_db, org_id=1)
        mock_record.assert_called()
        call_kwargs = mock_record.call_args
        assert call_kwargs.kwargs["job_name"] == "stale_task_check"
        assert call_kwargs.kwargs["status"] == "ok"


async def test_check_follow_up_contacts_records_job_run(mock_db):
    """_check_follow_up_contacts should record a successful run."""
    with (
        patch("app.services.contact.get_follow_up_due", new_callable=AsyncMock, return_value=[]) as mock_get,
        patch("app.services.sync_scheduler._record_job_run", new_callable=AsyncMock) as mock_record,
    ):
        await _check_follow_up_contacts(mock_db, org_id=1)
        mock_get.assert_called_once_with(mock_db, 1, limit=20)
        mock_record.assert_called()
        assert mock_record.call_args.kwargs["job_name"] == "contact_follow_up_check"


async def test_daily_briefing_notification_creates_notification(mock_db):
    """_maybe_emit_daily_briefing_notification should create a notification."""
    fake_dashboard = {
        "summary": {
            "total_members": 5,
            "members_with_plan": 3,
            "members_without_plan": ["Alice", "Bob"],
            "total_tasks_today": 10,
            "tasks_done": 4,
            "tasks_pending": 6,
            "pending_approvals": 2,
            "unread_emails": 8,
        },
    }
    with (
        patch("app.services.briefing.get_team_dashboard", new_callable=AsyncMock, return_value=fake_dashboard),
        patch("app.services.notification.create_notification", new_callable=AsyncMock) as mock_notif,
        patch("app.services.sync_scheduler._record_job_run", new_callable=AsyncMock),
    ):
        await _maybe_emit_daily_briefing_notification(mock_db, org_id=99)
        mock_notif.assert_called_once()
        call_kwargs = mock_notif.call_args.kwargs
        assert call_kwargs["type"] == "daily_briefing"
        assert call_kwargs["organization_id"] == 99
        assert "Team: 5 members" in call_kwargs["message"]


async def test_stale_task_check_handles_exception(mock_db):
    """_check_stale_tasks should handle exceptions gracefully and record error."""
    mock_db.execute.side_effect = RuntimeError("DB gone")

    with patch("app.services.sync_scheduler._record_job_run", new_callable=AsyncMock) as mock_record:
        await _check_stale_tasks(mock_db, org_id=1)
        mock_record.assert_called()
        assert mock_record.call_args.kwargs["status"] == "error"


async def test_scheduler_new_jobs_in_dispatch():
    """Manual dispatch supports the new job names."""
    import inspect

    from app.services import sync_scheduler

    source = inspect.getsource(sync_scheduler.replay_job_for_org)
    assert "stale_task_check" in source
    assert "contact_follow_up_check" in source
    assert "daily_briefing_notification" in source
