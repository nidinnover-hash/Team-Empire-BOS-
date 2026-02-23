from __future__ import annotations

import time


async def test_health_endpoint_latency_budget(client) -> None:
    start = time.perf_counter()
    response = await client.get("/api/v1/health")
    elapsed = time.perf_counter() - start
    assert response.status_code == 200
    assert elapsed < 1.0


async def test_openapi_endpoint_latency_budget(client) -> None:
    start = time.perf_counter()
    response = await client.get("/openapi.json")
    elapsed = time.perf_counter() - start
    assert response.status_code == 200
    assert elapsed < 2.0
