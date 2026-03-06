from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.core.deps import get_db
from app.main import app as fastapi_app
from app.models.signal import Signal
from tests.conftest import _make_auth_headers


async def _get_session():
    override = fastapi_app.dependency_overrides[get_db]
    agen = override()
    session = await agen.__anext__()
    return session, agen


async def _seed_signal_rows() -> None:
    session, agen = await _get_session()
    try:
        now = datetime.now(UTC)
        session.add_all(
            [
                Signal(
                    signal_id="sig-approval-requested-org1",
                    organization_id=1,
                    actor_user_id=1,
                    topic="approval.requested",
                    category="decision",
                    source="approval.service",
                    entity_type="approval",
                    entity_id="101",
                    correlation_id="corr-101",
                    occurred_at=now - timedelta(minutes=5),
                    payload_json={
                        "approval_id": 101,
                        "approval_type": "send_message",
                        "status": "pending",
                    },
                    metadata_json={},
                    summary_text="approval requested",
                    created_at=now - timedelta(minutes=5),
                ),
                Signal(
                    signal_id="sig-approval-approved-org1",
                    organization_id=1,
                    actor_user_id=1,
                    topic="approval.approved",
                    category="decision",
                    source="approval.service",
                    entity_type="approval",
                    entity_id="101",
                    correlation_id="corr-101",
                    occurred_at=now - timedelta(minutes=4),
                    payload_json={
                        "approval_id": 101,
                        "approval_type": "send_message",
                        "status": "approved",
                    },
                    metadata_json={},
                    summary_text="approval approved",
                    created_at=now - timedelta(minutes=4),
                ),
                Signal(
                    signal_id="sig-execution-started-org1",
                    organization_id=1,
                    actor_user_id=1,
                    topic="execution.started",
                    category="execution",
                    source="execution.service",
                    entity_type="execution",
                    entity_id="201",
                    correlation_id="corr-101",
                    occurred_at=now - timedelta(minutes=3),
                    payload_json={
                        "approval_id": 101,
                        "execution_id": 201,
                        "status": "running",
                    },
                    metadata_json={},
                    summary_text="execution started",
                    created_at=now - timedelta(minutes=3),
                ),
                Signal(
                    signal_id="sig-execution-failed-org1",
                    organization_id=1,
                    actor_user_id=1,
                    topic="execution.failed",
                    category="execution",
                    source="execution.service",
                    entity_type="execution",
                    entity_id="201",
                    correlation_id="corr-101",
                    occurred_at=now - timedelta(minutes=2),
                    payload_json={
                        "approval_id": 101,
                        "execution_id": 201,
                        "status": "failed",
                        "error_text": "SMTP failure",
                    },
                    metadata_json={},
                    summary_text="execution failed",
                    created_at=now - timedelta(minutes=2),
                ),
                Signal(
                    signal_id="sig-approval-requested-stalled-org1",
                    organization_id=1,
                    actor_user_id=1,
                    topic="approval.requested",
                    category="decision",
                    source="approval.service",
                    entity_type="approval",
                    entity_id="102",
                    correlation_id="corr-102",
                    occurred_at=now - timedelta(minutes=10),
                    payload_json={
                        "approval_id": 102,
                        "approval_type": "assign_task",
                        "status": "pending",
                    },
                    metadata_json={},
                    summary_text="approval requested",
                    created_at=now - timedelta(minutes=10),
                ),
                Signal(
                    signal_id="sig-approval-approved-stalled-org1",
                    organization_id=1,
                    actor_user_id=1,
                    topic="approval.approved",
                    category="decision",
                    source="approval.service",
                    entity_type="approval",
                    entity_id="102",
                    correlation_id="corr-102",
                    occurred_at=now - timedelta(minutes=9),
                    payload_json={
                        "approval_id": 102,
                        "approval_type": "assign_task",
                        "status": "approved",
                    },
                    metadata_json={},
                    summary_text="approval approved",
                    created_at=now - timedelta(minutes=9),
                ),
                Signal(
                    signal_id="sig-approval-requested-org2",
                    organization_id=2,
                    actor_user_id=2,
                    topic="approval.requested",
                    category="decision",
                    source="approval.service",
                    entity_type="approval",
                    entity_id="999",
                    correlation_id="corr-org2",
                    occurred_at=now - timedelta(minutes=1),
                    payload_json={
                        "approval_id": 999,
                        "approval_type": "spend_money",
                        "status": "pending",
                    },
                    metadata_json={},
                    summary_text="org2 approval",
                    created_at=now - timedelta(minutes=1),
                ),
                Signal(
                    signal_id="sig-ai-completed-openai-org1",
                    organization_id=1,
                    actor_user_id=1,
                    topic="ai.call.completed",
                    category="brain",
                    source="brain.router",
                    entity_type="ai_call",
                    entity_id="req-ai-ok",
                    correlation_id="corr-ai-1",
                    request_id="req-ai-ok",
                    occurred_at=now - timedelta(minutes=8),
                    payload_json={
                        "provider": "openai",
                        "model_name": "gpt-4o-mini",
                        "latency_ms": 120,
                        "used_fallback": False,
                        "error_type": None,
                        "request_id": "req-ai-ok",
                    },
                    metadata_json={},
                    summary_text="ai call completed",
                    created_at=now - timedelta(minutes=8),
                ),
                Signal(
                    signal_id="sig-ai-failed-groq-org1",
                    organization_id=1,
                    actor_user_id=1,
                    topic="ai.call.failed",
                    category="brain",
                    source="brain.router",
                    entity_type="ai_call",
                    entity_id="req-ai-fail",
                    correlation_id="corr-ai-2",
                    request_id="req-ai-fail",
                    occurred_at=now - timedelta(minutes=7),
                    payload_json={
                        "provider": "groq",
                        "model_name": "llama-3.3-70b-versatile",
                        "latency_ms": 860,
                        "used_fallback": True,
                        "fallback_from": "openai",
                        "error_type": "RateLimitError",
                        "request_id": "req-ai-fail",
                    },
                    metadata_json={},
                    summary_text="ai call failed",
                    created_at=now - timedelta(minutes=7),
                ),
                Signal(
                    signal_id="sig-ai-completed-openai-second-org1",
                    organization_id=1,
                    actor_user_id=1,
                    topic="ai.call.completed",
                    category="brain",
                    source="brain.router",
                    entity_type="ai_call",
                    entity_id="req-ai-ok-2",
                    correlation_id="corr-ai-3",
                    request_id="req-ai-ok-2",
                    occurred_at=now - timedelta(minutes=6),
                    payload_json={
                        "provider": "openai",
                        "model_name": "gpt-4.1-mini",
                        "latency_ms": 180,
                        "used_fallback": False,
                        "error_type": None,
                        "request_id": "req-ai-ok-2",
                    },
                    metadata_json={},
                    summary_text="ai call completed",
                    created_at=now - timedelta(minutes=6),
                ),
                Signal(
                    signal_id="sig-ai-failed-org2",
                    organization_id=2,
                    actor_user_id=2,
                    topic="ai.call.failed",
                    category="brain",
                    source="brain.router",
                    entity_type="ai_call",
                    entity_id="req-ai-org2",
                    correlation_id="corr-ai-org2",
                    request_id="req-ai-org2",
                    occurred_at=now - timedelta(minutes=1),
                    payload_json={
                        "provider": "anthropic",
                        "model_name": "claude-3-7-sonnet",
                        "latency_ms": 540,
                        "used_fallback": False,
                        "error_type": "TimeoutError",
                        "request_id": "req-ai-org2",
                    },
                    metadata_json={},
                    summary_text="org2 ai call failed",
                    created_at=now - timedelta(minutes=1),
                ),
                Signal(
                    signal_id="sig-scheduler-completed-org1",
                    organization_id=1,
                    actor_user_id=1,
                    topic="scheduler.job.completed",
                    category="system",
                    source="sync_scheduler",
                    entity_type="scheduler_job",
                    entity_id="nightly_sync",
                    correlation_id="corr-scheduler-1",
                    occurred_at=now - timedelta(minutes=12),
                    payload_json={
                        "job_name": "nightly_sync",
                        "status": "ok",
                        "duration_ms": 2200,
                        "details": {"integrations": 4},
                        "error": None,
                    },
                    metadata_json={},
                    summary_text="nightly_sync:ok",
                    created_at=now - timedelta(minutes=12),
                ),
                Signal(
                    signal_id="sig-scheduler-failed-org1",
                    organization_id=1,
                    actor_user_id=1,
                    topic="scheduler.job.failed",
                    category="system",
                    source="sync_scheduler",
                    entity_type="scheduler_job",
                    entity_id="retry_webhooks",
                    correlation_id="corr-scheduler-2",
                    occurred_at=now - timedelta(minutes=11),
                    payload_json={
                        "job_name": "retry_webhooks",
                        "status": "error",
                        "duration_ms": 900,
                        "details": {"attempted": 6},
                        "error": "network timeout",
                    },
                    metadata_json={},
                    summary_text="retry_webhooks:error",
                    created_at=now - timedelta(minutes=11),
                ),
                Signal(
                    signal_id="sig-scheduler-completed-second-org1",
                    organization_id=1,
                    actor_user_id=1,
                    topic="scheduler.job.completed",
                    category="system",
                    source="sync_scheduler",
                    entity_type="scheduler_job",
                    entity_id="retry_webhooks",
                    correlation_id="corr-scheduler-3",
                    occurred_at=now - timedelta(minutes=10),
                    payload_json={
                        "job_name": "retry_webhooks",
                        "status": "ok",
                        "duration_ms": 1100,
                        "details": {"attempted": 2},
                        "error": None,
                    },
                    metadata_json={},
                    summary_text="retry_webhooks:ok",
                    created_at=now - timedelta(minutes=10),
                ),
                Signal(
                    signal_id="sig-scheduler-failed-org2",
                    organization_id=2,
                    actor_user_id=2,
                    topic="scheduler.job.failed",
                    category="system",
                    source="sync_scheduler",
                    entity_type="scheduler_job",
                    entity_id="daily_digest",
                    correlation_id="corr-scheduler-org2",
                    occurred_at=now - timedelta(minutes=2),
                    payload_json={
                        "job_name": "daily_digest",
                        "status": "error",
                        "duration_ms": 1500,
                        "details": {"channels": 1},
                        "error": "slack unavailable",
                    },
                    metadata_json={},
                    summary_text="daily_digest:error",
                    created_at=now - timedelta(minutes=2),
                ),
                Signal(
                    signal_id="sig-webhook-succeeded-org1",
                    organization_id=1,
                    actor_user_id=1,
                    topic="webhook.delivery.succeeded",
                    category="execution",
                    source="webhook.dispatch",
                    entity_type="webhook_delivery",
                    entity_id="301",
                    correlation_id="corr-webhook-1",
                    occurred_at=now - timedelta(minutes=15),
                    payload_json={
                        "delivery_id": 301,
                        "endpoint_id": 10,
                        "event": "approval.approved",
                        "status": "success",
                        "attempt_count": 1,
                        "response_status_code": 200,
                        "duration_ms": 87,
                        "error_message": None,
                    },
                    metadata_json={},
                    summary_text="approval.approved:success",
                    created_at=now - timedelta(minutes=15),
                ),
                Signal(
                    signal_id="sig-webhook-failed-org1",
                    organization_id=1,
                    actor_user_id=1,
                    topic="webhook.delivery.failed",
                    category="execution",
                    source="webhook.retry",
                    entity_type="webhook_delivery",
                    entity_id="302",
                    correlation_id="corr-webhook-2",
                    occurred_at=now - timedelta(minutes=14),
                    payload_json={
                        "delivery_id": 302,
                        "endpoint_id": 11,
                        "event": "approval.rejected",
                        "status": "failed",
                        "attempt_count": 3,
                        "response_status_code": 500,
                        "duration_ms": 125,
                        "error_message": "HTTP 500",
                    },
                    metadata_json={},
                    summary_text="approval.rejected:failed",
                    created_at=now - timedelta(minutes=14),
                ),
                Signal(
                    signal_id="sig-webhook-succeeded-second-org1",
                    organization_id=1,
                    actor_user_id=1,
                    topic="webhook.delivery.succeeded",
                    category="execution",
                    source="webhook.dispatch",
                    entity_type="webhook_delivery",
                    entity_id="303",
                    correlation_id="corr-webhook-3",
                    occurred_at=now - timedelta(minutes=13),
                    payload_json={
                        "delivery_id": 303,
                        "endpoint_id": 11,
                        "event": "execution.completed",
                        "status": "success",
                        "attempt_count": 1,
                        "response_status_code": 202,
                        "duration_ms": 95,
                        "error_message": None,
                    },
                    metadata_json={},
                    summary_text="execution.completed:success",
                    created_at=now - timedelta(minutes=13),
                ),
                Signal(
                    signal_id="sig-webhook-failed-org2",
                    organization_id=2,
                    actor_user_id=2,
                    topic="webhook.delivery.failed",
                    category="execution",
                    source="webhook.retry",
                    entity_type="webhook_delivery",
                    entity_id="401",
                    correlation_id="corr-webhook-org2",
                    occurred_at=now - timedelta(minutes=3),
                    payload_json={
                        "delivery_id": 401,
                        "endpoint_id": 22,
                        "event": "scheduler.job.failed",
                        "status": "failed",
                        "attempt_count": 2,
                        "response_status_code": 503,
                        "duration_ms": 210,
                        "error_message": "upstream unavailable",
                    },
                    metadata_json={},
                    summary_text="scheduler.job.failed:failed",
                    created_at=now - timedelta(minutes=3),
                ),
            ]
        )
        await session.commit()
    finally:
        await agen.aclose()


async def test_observability_signals_filters_by_topic(client):
    await _seed_signal_rows()

    response = await client.get("/api/v1/observability/signals?topic=approval.approved&limit=20")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert all(row["topic"] == "approval.approved" for row in body)
    assert all(row["organization_id"] == 1 for row in body)


async def test_observability_signals_filters_by_correlation(client):
    await _seed_signal_rows()

    response = await client.get("/api/v1/observability/signals?correlation_id=corr-101&limit=20")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 4
    assert {row["correlation_id"] for row in body} == {"corr-101"}
    assert {row["organization_id"] for row in body} == {1}


async def test_decision_timeline_filters_by_approval_id(client):
    await _seed_signal_rows()

    response = await client.get("/api/v1/observability/decision-timeline?approval_id=101&limit=20")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["approval_id"] == 101
    assert body[0]["approval_status"] == "approved"
    assert body[0]["execution_status"] == "failed"
    assert body[0]["stalled"] is False
    assert len(body[0]["timeline"]) == 4


async def test_decision_timeline_filters_by_correlation_id(client):
    await _seed_signal_rows()

    response = await client.get("/api/v1/observability/decision-timeline?correlation_id=corr-102&limit=20")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["approval_id"] == 102
    assert body[0]["stalled"] is True
    assert body[0]["execution_status"] is None


async def test_decision_summary_filters_by_approval_id(client):
    await _seed_signal_rows()

    response = await client.get("/api/v1/observability/decision-summary?approval_id=101&limit=20")

    assert response.status_code == 200
    body = response.json()
    assert body["total_requests"] == 1
    assert body["approved_count"] == 1
    assert body["rejected_count"] == 0
    assert body["approved_but_not_executed_count"] == 0
    assert body["execution_failed_count"] == 1
    assert body["recent_failed"][0]["approval_id"] == 101


async def test_decision_summary_filters_by_correlation_id(client):
    await _seed_signal_rows()

    response = await client.get("/api/v1/observability/decision-summary?correlation_id=corr-102&limit=20")

    assert response.status_code == 200
    body = response.json()
    assert body["total_requests"] == 1
    assert body["approved_count"] == 1
    assert body["approved_but_not_executed_count"] == 1
    assert body["execution_failed_count"] == 0
    assert body["recent_stalled"][0]["approval_id"] == 102


async def test_signal_projection_endpoints_are_org_scoped(client):
    await _seed_signal_rows()
    org2_headers = _make_auth_headers(2, "ceo@org2.com", "CEO", 2)

    signals_response = await client.get(
        "/api/v1/observability/signals?topic=approval.requested&limit=20",
        headers=org2_headers,
    )
    assert signals_response.status_code == 200
    signals_body = signals_response.json()
    assert len(signals_body) == 1
    assert signals_body[0]["organization_id"] == 2
    assert signals_body[0]["entity_id"] == "999"

    timeline_response = await client.get(
        "/api/v1/observability/decision-timeline?correlation_id=corr-org2&limit=20",
        headers=org2_headers,
    )
    assert timeline_response.status_code == 200
    timeline_body = timeline_response.json()
    assert len(timeline_body) == 1
    assert timeline_body[0]["approval_id"] == 999

    summary_response = await client.get(
        "/api/v1/observability/decision-summary?correlation_id=corr-org2&limit=20",
        headers=org2_headers,
    )
    assert summary_response.status_code == 200
    summary_body = summary_response.json()
    assert summary_body["total_requests"] == 1
    assert summary_body["pending_count"] == 1


async def test_ai_reliability_projection_aggregates_signal_metrics(client):
    await _seed_signal_rows()

    response = await client.get("/api/v1/observability/ai-reliability?limit=50")

    assert response.status_code == 200
    body = response.json()
    assert body["total_calls"] == 3
    assert body["failed_calls"] == 1
    assert body["fallback_count"] == 1
    assert body["success_rate"] == 66.7
    assert body["error_rate"] == 33.3
    assert body["avg_latency_ms"] == 386
    assert len(body["providers"]) == 2
    assert body["providers"][0]["provider"] == "openai"
    assert body["providers"][0]["total_calls"] == 2
    assert body["providers"][0]["failed_calls"] == 0
    assert body["providers"][1]["provider"] == "groq"
    assert body["providers"][1]["failed_calls"] == 1
    assert body["recent_failures"][0]["request_id"] == "req-ai-fail"


async def test_ai_reliability_projection_is_org_scoped(client):
    await _seed_signal_rows()
    org2_headers = _make_auth_headers(2, "ceo@org2.com", "CEO", 2)

    response = await client.get("/api/v1/observability/ai-reliability?limit=50", headers=org2_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["total_calls"] == 1
    assert body["failed_calls"] == 1
    assert body["providers"][0]["provider"] == "anthropic"
    assert body["recent_failures"][0]["request_id"] == "req-ai-org2"


async def test_scheduler_health_projection_aggregates_signal_metrics(client):
    await _seed_signal_rows()

    response = await client.get("/api/v1/observability/scheduler-health?limit=50")

    assert response.status_code == 200
    body = response.json()
    assert body["total_runs"] == 3
    assert body["failed_runs"] == 1
    assert body["success_rate"] == 66.7
    assert body["avg_duration_ms"] == 1400
    assert len(body["jobs"]) == 2
    assert body["jobs"][0]["job_name"] == "retry_webhooks"
    assert body["jobs"][0]["failed_runs"] == 1
    assert body["jobs"][0]["total_runs"] == 2
    assert body["jobs"][1]["job_name"] == "nightly_sync"
    assert body["recent_failures"][0]["job_name"] == "retry_webhooks"
    assert body["recent_failures"][0]["error"] == "network timeout"


async def test_scheduler_health_projection_is_org_scoped(client):
    await _seed_signal_rows()
    org2_headers = _make_auth_headers(2, "ceo@org2.com", "CEO", 2)

    response = await client.get("/api/v1/observability/scheduler-health?limit=50", headers=org2_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["total_runs"] == 1
    assert body["failed_runs"] == 1
    assert body["jobs"][0]["job_name"] == "daily_digest"
    assert body["recent_failures"][0]["error"] == "slack unavailable"


async def test_webhook_reliability_projection_aggregates_signal_metrics(client):
    await _seed_signal_rows()

    response = await client.get("/api/v1/observability/webhook-reliability?limit=50")

    assert response.status_code == 200
    body = response.json()
    assert body["total_deliveries"] == 3
    assert body["failed_deliveries"] == 1
    assert body["success_rate"] == 66.7
    assert body["avg_duration_ms"] == 102
    assert len(body["endpoints"]) == 2
    assert body["endpoints"][0]["endpoint_id"] == 11
    assert body["endpoints"][0]["failed_deliveries"] == 1
    assert body["endpoints"][0]["total_deliveries"] == 2
    assert body["recent_failures"][0]["event"] == "approval.rejected"
    assert body["recent_failures"][0]["error_message"] == "HTTP 500"


async def test_webhook_reliability_projection_is_org_scoped(client):
    await _seed_signal_rows()
    org2_headers = _make_auth_headers(2, "ceo@org2.com", "CEO", 2)

    response = await client.get("/api/v1/observability/webhook-reliability?limit=50", headers=org2_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["total_deliveries"] == 1
    assert body["failed_deliveries"] == 1
    assert body["endpoints"][0]["endpoint_id"] == 22
    assert body["recent_failures"][0]["error_message"] == "upstream unavailable"
