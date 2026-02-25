from app.core.config import settings
from app.core import middleware


class _FakeRedis:
    def __init__(self) -> None:
        self._sets: dict[str, dict[str, int]] = {}

    def zremrangebyscore(self, key: str, min: int | float | str, max: int | float | str) -> int:
        upper = int(float(max))
        bucket = self._sets.get(key, {})
        before = len(bucket)
        self._sets[key] = {member: score for member, score in bucket.items() if score > upper}
        return before - len(self._sets[key])

    def zcard(self, key: str) -> int:
        return len(self._sets.get(key, {}))

    def zadd(self, key: str, mapping: dict[str, int]) -> int:
        bucket = self._sets.setdefault(key, {})
        before = len(bucket)
        bucket.update(mapping)
        return len(bucket) - before

    def expire(self, key: str, seconds: int) -> bool:
        _ = key
        _ = seconds
        return True

    def delete(self, key: str) -> int:
        if key in self._sets:
            del self._sets[key]
            return 1
        return 0

    def ping(self) -> bool:
        return True


def test_login_lockout_uses_redis_backend(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(settings, "RATE_LIMIT_BACKEND", "redis", raising=False)
    monkeypatch.setattr(settings, "RATE_LIMIT_REDIS_URL", "redis://example:6379/0", raising=False)
    monkeypatch.setattr(middleware, "_get_redis_client", lambda: fake)

    ip = "127.0.0.1"
    for _ in range(middleware.LOGIN_FAIL_MAX):
        assert middleware.check_login_allowed(ip) is True
        middleware.record_login_failure(ip)

    assert middleware.check_login_allowed(ip) is False
    middleware.clear_login_failures(ip)
    assert middleware.check_login_allowed(ip) is True
