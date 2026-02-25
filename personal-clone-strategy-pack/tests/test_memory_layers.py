from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

from app.memory.retrieval import build_typed_context, rank_context_layers
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


def test_rank_context_layers_prefers_critical_daily_signal() -> None:
    now = datetime(2026, 2, 24, 10, 0, tzinfo=timezone.utc)
    ranked = rank_context_layers(
        [
            {
                "layer_type": "profile",
                "source": "manual",
                "priority": 1,
                "content": "PROFILE:\n- founder: nidin",
                "char_count": 20,
            },
            {
                "layer_type": "daily",
                "source": "risk",
                "priority": 3,
                "content": "[RISK]:\ncritical deploy gap",
                "char_count": 26,
                "created_at": "2026-02-24T09:55:00+00:00",
            },
        ],
        now=now,
        debug=True,
    )
    assert ranked[0]["layer_type"] == "daily"
    assert ranked[0]["source"] == "risk"
    assert any("critical_source_boost" in item for item in ranked[0].get("explain", []))


def test_rank_context_layers_applies_stale_decay() -> None:
    now = datetime(2026, 2, 24, 10, 0, tzinfo=timezone.utc)
    ranked = rank_context_layers(
        [
            {
                "layer_type": "daily",
                "source": "priority",
                "priority": 3,
                "content": "[PRIORITY]:\nnew",
                "char_count": 16,
                "created_at": "2026-02-24T09:55:00+00:00",
            },
            {
                "layer_type": "daily",
                "source": "priority",
                "priority": 3,
                "content": "[PRIORITY]:\nold",
                "char_count": 16,
                "created_at": "2026-02-20T09:55:00+00:00",
            },
        ],
        now=now,
    )
    assert ranked[0]["content"].endswith("new")
    assert ranked[0]["score"] > ranked[1]["score"]


def test_rank_context_layers_deterministic_tie_break() -> None:
    ranked = rank_context_layers(
        [
            {
                "layer_type": "team",
                "source": "manual",
                "priority": 2,
                "content": "TEAM:\n- B",
                "char_count": 10,
            },
            {
                "layer_type": "team",
                "source": "manual",
                "priority": 2,
                "content": "TEAM:\n- A",
                "char_count": 10,
            },
        ],
    )
    assert ranked[0]["content"].endswith("A")


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

    memory_service.invalidate_memory_cache(1)
    context = await memory_service.build_memory_context(
        db=_FakeDB(),
        organization_id=1,
        char_limit=4000,
    )
    assert "INTEGRATIONS:" in context
    assert "clickup: connected" in context


def test_build_typed_context_debug_includes_explain() -> None:
    profile = [ProfileMemory(organization_id=1, key="k", value="v", category="fact")]
    layers = build_typed_context(
        profile_entries=profile,
        team_members=[],
        daily_contexts=[],
        integration_statuses=[],
        debug=True,
    )
    assert layers
    assert "score" in layers[0]
    assert "explain" in layers[0]
