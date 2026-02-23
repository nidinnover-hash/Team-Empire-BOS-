from __future__ import annotations

from app.core.deps import get_db
from app.core.security import create_access_token
from app.main import app as fastapi_app
from app.models.ai_call_log import AiCallLog
from app.models.approval import Approval
from app.models.decision_trace import DecisionTrace


def _auth_headers(user_id: int, email: str, role: str, org_id: int) -> dict[str, str]:
    token = create_access_token(
        {"id": user_id, "email": email, "role": role, "org_id": org_id}
    )
    return {"Authorization": f"Bearer {token}"}


async def _create_second_org(client, headers: dict[str, str]) -> int:
    response = await client.post(
        "/api/v1/orgs",
        json={"name": "Org Two", "slug": "org-two"},
        headers=headers,
    )
    assert response.status_code == 201
    return int(response.json()["id"])


async def _seed_observability_rows() -> None:
    override = fastapi_app.dependency_overrides[get_db]
    agen = override()
    session = await agen.__anext__()
    try:
        session.add_all(
            [
                AiCallLog(
                    organization_id=1,
                    provider="openai",
                    model_name="gpt-4",
                    latency_ms=120,
                    used_fallback=False,
                    request_id="req-org1",
                ),
                AiCallLog(
                    organization_id=2,
                    provider="groq",
                    model_name="llama3",
                    latency_ms=80,
                    used_fallback=False,
                    request_id="req-org2",
                ),
                DecisionTrace(
                    organization_id=1,
                    trace_type="daily_run",
                    title="Org1 trace",
                    summary="Org1 summary",
                    confidence_score=0.8,
                    request_id="trace-org1",
                ),
                DecisionTrace(
                    organization_id=2,
                    trace_type="daily_run",
                    title="Org2 trace",
                    summary="Org2 summary",
                    confidence_score=0.6,
                    request_id="trace-org2",
                ),
                Approval(
                    organization_id=1,
                    approval_type="send_message",
                    requested_by=1,
                    payload_json={"k": "v"},
                    status="pending",
                ),
                Approval(
                    organization_id=2,
                    approval_type="send_message",
                    requested_by=2,
                    payload_json={"k": "v"},
                    status="pending",
                ),
            ]
        )
        await session.commit()
    finally:
        await agen.aclose()


async def test_observability_endpoints_are_org_scoped(client):
    ceo_org1 = _auth_headers(1, "ceo@org1.com", "CEO", 1)
    await _create_second_org(client, ceo_org1)
    await _seed_observability_rows()

    summary_resp = await client.get("/api/v1/observability/summary", headers=ceo_org1)
    assert summary_resp.status_code == 200
    summary = summary_resp.json()
    assert summary["total_ai_calls"] == 1
    assert summary["total_approvals"] == 1
    assert summary["provider_stats"][0]["provider"] == "openai"
    assert "runtime_stats" in summary

    ai_calls_resp = await client.get("/api/v1/observability/ai-calls", headers=ceo_org1)
    assert ai_calls_resp.status_code == 200
    ai_calls = ai_calls_resp.json()
    assert len(ai_calls) == 1
    assert ai_calls[0]["request_id"] == "req-org1"
    assert ai_calls[0]["provider"] == "openai"

    traces_resp = await client.get("/api/v1/observability/decision-traces", headers=ceo_org1)
    assert traces_resp.status_code == 200
    traces = traces_resp.json()
    assert len(traces) == 1
    assert traces[0]["request_id"] == "trace-org1"
    assert traces[0]["title"] == "Org1 trace"


async def test_observability_isolation_for_org2_actor(client):
    ceo_org1 = _auth_headers(1, "ceo@org1.com", "CEO", 1)
    await _create_second_org(client, ceo_org1)
    await _seed_observability_rows()
    ceo_org2 = _auth_headers(2, "ceo@org2.com", "CEO", 2)

    summary_resp = await client.get("/api/v1/observability/summary", headers=ceo_org2)
    assert summary_resp.status_code == 200
    summary = summary_resp.json()
    assert summary["total_ai_calls"] == 1
    assert summary["total_approvals"] == 1
    assert summary["provider_stats"][0]["provider"] == "groq"
    assert "runtime_stats" in summary

    ai_calls_resp = await client.get("/api/v1/observability/ai-calls", headers=ceo_org2)
    assert ai_calls_resp.status_code == 200
    ai_calls = ai_calls_resp.json()
    assert len(ai_calls) == 1
    assert ai_calls[0]["request_id"] == "req-org2"
    assert ai_calls[0]["provider"] == "groq"

    traces_resp = await client.get("/api/v1/observability/decision-traces", headers=ceo_org2)
    assert traces_resp.status_code == 200
    traces = traces_resp.json()
    assert len(traces) == 1
    assert traces[0]["request_id"] == "trace-org2"
    assert traces[0]["title"] == "Org2 trace"
