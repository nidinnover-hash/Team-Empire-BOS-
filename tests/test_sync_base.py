"""Tests for the IntegrationSync base class and the three refactored services."""
from __future__ import annotations

import asyncio
import inspect
from datetime import UTC, datetime
from typing import Any, Hashable
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.db.base import Base as ORMBase
from app.services.sync_base import IntegrationSync, SyncResult


async def _await_retry(operation, **_kw):
    """Test stand-in for run_with_retry that just calls + awaits the operation."""
    result = operation()
    if inspect.isawaitable(result):
        return await result
    return result


# ---------------------------------------------------------------------------
# Concrete stub for testing the template method
# ---------------------------------------------------------------------------

class _StubModel:
    """Minimal ORM-like stand-in."""
    def __init__(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)


class StubSync(IntegrationSync):
    """Concrete subclass for testing the base class template method."""

    provider = "stub"

    def __init__(
        self,
        items: list[dict[str, Any]] | None = None,
        existing_keys: set[Hashable] | None = None,
        *,
        raise_on_fetch: Exception | None = None,
        raise_on_item: Exception | None = None,
    ) -> None:
        self._items = items or []
        self._existing_keys = existing_keys or set()
        self._raise_on_fetch = raise_on_fetch
        self._raise_on_item = raise_on_item
        self._converted: list[dict[str, Any]] = []

    async def fetch_items(self, token: str, config: dict[str, Any], **kwargs: Any) -> list[dict[str, Any]]:
        if self._raise_on_fetch:
            raise self._raise_on_fetch
        return self._items

    async def load_existing_keys(self, db: Any, org_id: int) -> set[Hashable]:
        return set(self._existing_keys)

    def dedup_key(self, item: dict[str, Any]) -> Hashable:
        if self._raise_on_item and item.get("bad"):
            raise self._raise_on_item
        return item["key"]

    def to_model(self, item: dict[str, Any], org_id: int) -> Any:
        self._converted.append(item)
        return _StubModel(org_id=org_id, **item)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_integration(*, connected: bool = True, token: str = "tok") -> MagicMock:
    integ = MagicMock()
    integ.status = "connected" if connected else "disconnected"
    integ.config_json = {"access_token": token}
    integ.last_sync_at = datetime.now(UTC)
    return integ


# ---------------------------------------------------------------------------
# SyncResult unit tests
# ---------------------------------------------------------------------------

class TestSyncResult:
    def test_to_dict_basic(self):
        r = SyncResult(provider="x", synced=3, skipped=1)
        d = r.to_dict()
        assert d["synced"] == 3
        assert d["skipped"] == 1
        assert "last_sync_at" in d

    def test_to_dict_with_extra(self):
        r = SyncResult(provider="x", extra={"pages_synced": 10})
        d = r.to_dict()
        assert d["pages_synced"] == 10

    def test_to_dict_errors_omitted_when_empty(self):
        r = SyncResult(provider="x")
        assert "errors" not in r.to_dict()

    def test_to_dict_errors_present(self):
        r = SyncResult(provider="x", errors=["fail"])
        assert r.to_dict()["errors"] == ["fail"]


# ---------------------------------------------------------------------------
# IntegrationSync.sync() template method tests
# ---------------------------------------------------------------------------

class TestIntegrationSyncTemplate:
    @pytest.mark.asyncio
    async def test_not_connected_raises(self):
        syncer = StubSync()
        with patch("app.services.sync_base.get_integration_by_type", new_callable=AsyncMock, return_value=None):
            with pytest.raises(ValueError, match="not connected"):
                await syncer.sync(AsyncMock(), org_id=1)

    @pytest.mark.asyncio
    async def test_disconnected_raises(self):
        syncer = StubSync()
        integ = _make_integration(connected=False)
        with patch("app.services.sync_base.get_integration_by_type", new_callable=AsyncMock, return_value=integ):
            with pytest.raises(ValueError, match="not connected"):
                await syncer.sync(AsyncMock(), org_id=1)

    @pytest.mark.asyncio
    async def test_happy_path_syncs_items(self):
        items = [{"key": "a", "val": 1}, {"key": "b", "val": 2}]
        syncer = StubSync(items=items)
        integ = _make_integration()
        db = AsyncMock()
        db.add = MagicMock()
        with (
            patch("app.services.sync_base.get_integration_by_type", new_callable=AsyncMock, return_value=integ),
            patch("app.services.sync_base.mark_sync_time", new_callable=AsyncMock) as mock_mark,
            patch("app.services.sync_base.run_with_retry", new=_await_retry),
        ):
            result = await syncer.sync(db, org_id=1)

        assert result.synced == 2
        assert result.skipped == 0
        assert len(result.errors) == 0
        assert db.add.call_count == 2
        db.commit.assert_awaited_once()
        mock_mark.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_dedup_skips_existing(self):
        items = [{"key": "a"}, {"key": "b"}, {"key": "c"}]
        syncer = StubSync(items=items, existing_keys={"a", "c"})
        integ = _make_integration()
        db = AsyncMock()
        db.add = MagicMock()
        with (
            patch("app.services.sync_base.get_integration_by_type", new_callable=AsyncMock, return_value=integ),
            patch("app.services.sync_base.mark_sync_time", new_callable=AsyncMock),
            patch("app.services.sync_base.run_with_retry", new=_await_retry),
        ):
            result = await syncer.sync(db, org_id=1)

        assert result.synced == 1
        assert result.skipped == 2

    @pytest.mark.asyncio
    async def test_intra_batch_dedup(self):
        items = [{"key": "x"}, {"key": "x"}, {"key": "x"}]
        syncer = StubSync(items=items)
        integ = _make_integration()
        db = AsyncMock()
        db.add = MagicMock()
        with (
            patch("app.services.sync_base.get_integration_by_type", new_callable=AsyncMock, return_value=integ),
            patch("app.services.sync_base.mark_sync_time", new_callable=AsyncMock),
            patch("app.services.sync_base.run_with_retry", new=_await_retry),
        ):
            result = await syncer.sync(db, org_id=1)

        assert result.synced == 1
        assert result.skipped == 2

    @pytest.mark.asyncio
    async def test_per_item_error_doesnt_crash(self):
        items = [{"key": "ok"}, {"key": "z", "bad": True}, {"key": "ok2"}]
        syncer = StubSync(items=items, raise_on_item=ValueError("boom"))
        integ = _make_integration()
        db = AsyncMock()
        db.add = MagicMock()
        with (
            patch("app.services.sync_base.get_integration_by_type", new_callable=AsyncMock, return_value=integ),
            patch("app.services.sync_base.mark_sync_time", new_callable=AsyncMock),
            patch("app.services.sync_base.run_with_retry", new=_await_retry),
        ):
            result = await syncer.sync(db, org_id=1)

        assert result.synced == 2
        assert result.skipped == 1
        assert len(result.errors) == 1
        assert "boom" in result.errors[0]

    @pytest.mark.asyncio
    async def test_fetch_failure_returns_error(self):
        syncer = StubSync(raise_on_fetch=RuntimeError("API down"))
        integ = _make_integration()
        db = AsyncMock()
        with (
            patch("app.services.sync_base.get_integration_by_type", new_callable=AsyncMock, return_value=integ),
            patch("app.services.sync_base.mark_sync_time", new_callable=AsyncMock) as mock_mark,
            patch("app.services.sync_base.run_with_retry", new=_await_retry),
        ):
            result = await syncer.sync(db, org_id=1)

        assert result.synced == 0
        assert len(result.errors) == 1
        assert "API down" in result.errors[0]
        # mark_sync_time still called even on fetch failure
        mock_mark.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_commit_when_zero_synced(self):
        syncer = StubSync(items=[{"key": "a"}], existing_keys={"a"})
        integ = _make_integration()
        db = AsyncMock()
        with (
            patch("app.services.sync_base.get_integration_by_type", new_callable=AsyncMock, return_value=integ),
            patch("app.services.sync_base.mark_sync_time", new_callable=AsyncMock),
            patch("app.services.sync_base.run_with_retry", new=_await_retry),
        ):
            result = await syncer.sync(db, org_id=1)

        assert result.synced == 0
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_kwargs_forwarded_to_fetch(self):
        syncer = StubSync()
        integ = _make_integration()
        db = AsyncMock()
        captured: dict[str, Any] = {}

        async def _spy_fetch(token: str, config: dict, **kw: Any) -> list:
            captured.update(kw)
            return []

        syncer.fetch_items = _spy_fetch  # type: ignore[assignment]
        with (
            patch("app.services.sync_base.get_integration_by_type", new_callable=AsyncMock, return_value=integ),
            patch("app.services.sync_base.mark_sync_time", new_callable=AsyncMock),
            patch("app.services.sync_base.run_with_retry", new=_await_retry),
        ):
            await syncer.sync(db, org_id=1, query="test", max_pages=5)

        assert captured["query"] == "test"
        assert captured["max_pages"] == 5


# ---------------------------------------------------------------------------
# Integration-level: verify public API functions still work
# ---------------------------------------------------------------------------

class TestNotionSyncWrapper:
    @pytest.mark.asyncio
    async def test_sync_pages_to_notes_calls_base(self, monkeypatch: pytest.MonkeyPatch):
        from app.services import notion_service

        fake_result = SyncResult(provider="notion", synced=3, skipped=2)
        fake_result.last_sync_at = datetime(2026, 1, 1, tzinfo=UTC)

        mock_sync = AsyncMock(return_value=fake_result)
        monkeypatch.setattr(notion_service._notion_sync, "sync", mock_sync)

        result = await notion_service.sync_pages_to_notes(AsyncMock(), org_id=1, query="hello")
        assert result["notes_created"] == 3
        assert result["pages_synced"] == 5  # synced + skipped
        mock_sync.assert_awaited_once()


class TestHubSpotSyncWrapper:
    @pytest.mark.asyncio
    async def test_sync_hubspot_data_calls_base(self, monkeypatch: pytest.MonkeyPatch):
        from app.services import hubspot_service

        fake_contact_result = SyncResult(provider="hubspot", synced=5, skipped=1)
        fake_contact_result.last_sync_at = datetime(2026, 1, 1, tzinfo=UTC)
        fake_deal_result = SyncResult(provider="hubspot", synced=3, skipped=0)
        fake_deal_result.last_sync_at = datetime(2026, 1, 1, tzinfo=UTC)

        monkeypatch.setattr(hubspot_service._hubspot_sync, "sync", AsyncMock(return_value=fake_contact_result))
        monkeypatch.setattr(hubspot_service._hubspot_deal_sync, "sync", AsyncMock(return_value=fake_deal_result))

        result = await hubspot_service.sync_hubspot_data(AsyncMock(), org_id=1)
        assert result["contacts_synced"] == 5
        assert result["deals_synced"] == 3


class TestCalendlySyncWrapper:
    @pytest.mark.asyncio
    async def test_sync_events_calls_base(self, monkeypatch: pytest.MonkeyPatch):
        from app.services import calendly_service

        fake_result = SyncResult(provider="calendly", synced=4, skipped=2)
        fake_result.last_sync_at = datetime(2026, 1, 1, tzinfo=UTC)

        mock_sync = AsyncMock(return_value=fake_result)
        monkeypatch.setattr(calendly_service._calendly_sync, "sync", mock_sync)

        result = await calendly_service.sync_events(AsyncMock(), org_id=1, days_ahead=3)
        assert result["events_synced"] == 4
        assert result["upcoming_events"] == 6  # synced + skipped
        mock_sync.assert_awaited_once()
