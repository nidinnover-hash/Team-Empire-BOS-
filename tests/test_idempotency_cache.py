import pytest

from app.core import idempotency
from app.core.config import settings


@pytest.fixture(autouse=True)
def reset_idempotency_state(monkeypatch):
    idempotency._cache.clear()
    monkeypatch.setattr(idempotency, "_redis_client", None)
    monkeypatch.setattr(idempotency, "_redis_initialized", False)
    monkeypatch.setattr(settings, "IDEMPOTENCY_BACKEND", "memory", raising=False)
    monkeypatch.setattr(settings, "IDEMPOTENCY_REDIS_URL", None, raising=False)
    monkeypatch.setattr(settings, "IDEMPOTENCY_TTL_SECONDS", 1800, raising=False)
    monkeypatch.setattr(settings, "IDEMPOTENCY_MAX_ITEMS", 5000, raising=False)
    monkeypatch.setattr(settings, "IDEMPOTENCY_REDIS_PREFIX", "pc:idempotency", raising=False)


def test_idempotency_returns_detached_payload_copy():
    scope = "ops_daily_run:1:*:5"
    key = "k1"
    payload = {"status": "ok", "nested": {"count": 1}, "ids": [1, 2]}
    idempotency.store_response(scope, key, payload)

    first = idempotency.get_cached_response(scope, key)
    assert first is not None
    first["nested"]["count"] = 99
    first["ids"].append(3)

    second = idempotency.get_cached_response(scope, key)
    assert second is not None
    assert second["nested"]["count"] == 1
    assert second["ids"] == [1, 2]


def test_idempotency_uses_redis_backend_when_available(monkeypatch):
    class FakeRedis:
        def __init__(self) -> None:
            self.store: dict[str, str] = {}
            self.setex_calls = 0

        def get(self, key: str):
            return self.store.get(key)

        def setex(self, key: str, time: int, value: str):
            self.setex_calls += 1
            self.store[key] = value
            return True

    fake = FakeRedis()
    monkeypatch.setattr(settings, "IDEMPOTENCY_BACKEND", "redis", raising=False)
    monkeypatch.setattr(settings, "IDEMPOTENCY_REDIS_URL", "redis://example:6379/0", raising=False)
    monkeypatch.setattr(idempotency, "_get_redis_client", lambda: fake)

    payload = {"ok": True}
    idempotency.store_response("email_sync:1", "k2", payload)
    hit = idempotency.get_cached_response("email_sync:1", "k2")

    assert hit == {"ok": True}
    assert fake.setex_calls == 1
    assert idempotency._cache == {}


def test_idempotency_falls_back_to_memory_when_redis_unavailable(monkeypatch):
    monkeypatch.setattr(settings, "IDEMPOTENCY_BACKEND", "redis", raising=False)
    monkeypatch.setattr(settings, "IDEMPOTENCY_REDIS_URL", "redis://example:6379/0", raising=False)
    monkeypatch.setattr(idempotency, "_get_redis_client", lambda: None)

    idempotency.store_response("email_sync:1", "k3", {"status": "memory"})
    hit = idempotency.get_cached_response("email_sync:1", "k3")

    assert hit == {"status": "memory"}
    assert len(idempotency._cache) == 1


def test_idempotency_conflict_when_fingerprint_differs():
    scope = "email_send:1:10"
    key = "same-key"
    fp_a = idempotency.build_fingerprint({"org_id": 1, "email_id": 10, "action": "send"})
    fp_b = idempotency.build_fingerprint({"org_id": 1, "email_id": 11, "action": "send"})
    idempotency.store_response(scope, key, {"status": "sent"}, fingerprint=fp_a)
    try:
        _ = idempotency.get_cached_response(scope, key, fingerprint=fp_b)
        raise AssertionError("expected idempotency conflict")
    except idempotency.IdempotencyConflictError:
        pass
