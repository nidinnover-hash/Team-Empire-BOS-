from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

from app.memory.retrieval import build_typed_context
from app.models.memory import DailyContext, ProfileMemory, TeamMember
from app.services import memory as memory_service


def test_build_typed_context_includes_integration_layer() -> None:
    profile = [ProfileMemory(organization_id=1, key="company", value="Nidin AI", category="fact")]
    members = [TeamMember(organization_id=1, name="Asha", role_title="Developer")]
    daily = [
        DailyContext(
            organization_id=1,
            date=date.today(),
            context_type="priority",
            content="Ship observability improvements",
        )
    ]
    layers = build_typed_context(
        profile_entries=profile,
        team_members=members,
        daily_contexts=daily,
        integration_statuses=[
            {"type": "gmail", "status": "connected", "last_sync_at": "2026-02-23T10:00:00Z"},
        ],
    )
    integration_layer = next((layer for layer in layers if layer.get("layer_type") == "integration"), None)
    assert integration_layer is not None
    assert "INTEGRATIONS:" in str(integration_layer.get("content"))
    assert "gmail: connected" in str(integration_layer.get("content"))


class _FakeScalars:
    def all(self) -> list:
        return []


class _FakeResult:
    def scalars(self) -> _FakeScalars:
        return _FakeScalars()


class _FakeDB:
    async def execute(self, *_args, **_kwargs) -> _FakeResult:
        return _FakeResult()


async def test_build_memory_context_appends_integration_block(monkeypatch) -> None:
    async def _empty_profile(*_args, **_kwargs):
        return []

    async def _empty_members(*_args, **_kwargs):
        return []

    async def _empty_daily(*_args, **_kwargs):
        return []

    async def _integration_status(*_args, **_kwargs):
        return [
            SimpleNamespace(
                type="clickup",
                status="connected",
                last_sync_at=datetime(2026, 2, 23, 10, 0, 0, tzinfo=timezone.utc),
            )
        ]

    monkeypatch.setattr(memory_service, "get_profile_memory", _empty_profile)
    monkeypatch.setattr(memory_service, "get_team_members", _empty_members)
    monkeypatch.setattr(memory_service, "get_daily_context", _empty_daily)
    monkeypatch.setattr("app.services.integration.list_integrations", _integration_status)

    context = await memory_service.build_memory_context(
        db=_FakeDB(),
        organization_id=1,
        char_limit=4000,
    )
    assert "INTEGRATIONS:" in context
    assert "clickup: connected" in context
