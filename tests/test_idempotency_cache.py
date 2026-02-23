from app.core.idempotency import _cache, get_cached_response, store_response


def test_idempotency_returns_detached_payload_copy():
    _cache.clear()
    scope = "ops_daily_run:1:*:5"
    key = "k1"
    payload = {"status": "ok", "nested": {"count": 1}, "ids": [1, 2]}
    store_response(scope, key, payload)

    first = get_cached_response(scope, key)
    assert first is not None
    first["nested"]["count"] = 99
    first["ids"].append(3)

    second = get_cached_response(scope, key)
    assert second is not None
    assert second["nested"]["count"] == 1
    assert second["ids"] == [1, 2]
