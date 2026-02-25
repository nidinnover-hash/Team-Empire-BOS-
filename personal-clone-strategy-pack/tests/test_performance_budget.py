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


async def test_root_health_endpoint_latency_budget(client) -> None:
    start = time.perf_counter()
    response = await client.get("/health")
    elapsed = time.perf_counter() - start
    assert response.status_code == 200
    assert elapsed < 0.5


def _p95(samples: list[float]) -> float:
    ordered = sorted(samples)
    idx = max(0, int(len(ordered) * 0.95) - 1)
    return ordered[idx]


async def test_health_endpoint_p95_budget(client) -> None:
    samples: list[float] = []
    for _ in range(20):
        start = time.perf_counter()
        response = await client.get("/api/v1/health")
        samples.append(time.perf_counter() - start)
        assert response.status_code == 200
    assert _p95(samples) < 0.8
