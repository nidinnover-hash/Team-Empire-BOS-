from datetime import UTC, datetime, timedelta

from app.core.deps import get_db
from app.main import app as fastapi_app
from app.models.ceo_control import SchedulerJobRun
from app.models.webhook import WebhookDelivery


async def _get_session():
    override = fastapi_app.dependency_overrides[get_db]
    agen = override()
    session = await agen.__anext__()
    return session, agen


async def test_control_webhook_reliability_metrics(client):
    create_resp = await client.post(
        "/api/v1/webhooks",
        json={"url": "https://example.com/hook"},
    )
    assert create_resp.status_code == 201
    endpoint_id = int(create_resp.json()["id"])
    now = datetime.now(UTC)

    session, agen = await _get_session()
    try:
        session.add(
            WebhookDelivery(
                webhook_endpoint_id=endpoint_id,
                organization_id=1,
                event="approval.created",
                payload_json={"k": 1},
                status="success",
                created_at=now - timedelta(minutes=40),
            )
        )
        session.add(
            WebhookDelivery(
                webhook_endpoint_id=endpoint_id,
                organization_id=1,
                event="approval.created",
                payload_json={"k": 2},
                status="failed",
                error_message="TimeoutError: request timed out",
                created_at=now - timedelta(minutes=30),
            )
        )
        replayed_original = WebhookDelivery(
            webhook_endpoint_id=endpoint_id,
            organization_id=1,
            event="approval.created",
            payload_json={"k": 3},
            status="replayed",
            created_at=now - timedelta(minutes=20),
        )
        session.add(replayed_original)
        session.add(
            WebhookDelivery(
                webhook_endpoint_id=endpoint_id,
                organization_id=1,
                event="approval.created",
                payload_json={"k": 3},
                status="success",
                created_at=now - timedelta(minutes=10),
            )
        )
        session.add(
            WebhookDelivery(
                webhook_endpoint_id=endpoint_id,
                organization_id=1,
                event="approval.created",
                payload_json={"k": 4},
                status="dead_letter",
                response_status_code=503,
                error_message="HTTP 503",
                created_at=now - timedelta(minutes=5),
            )
        )
        await session.commit()
    finally:
        await agen.aclose()

    resp = await client.get("/api/v1/control/webhook/reliability")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_deliveries"] >= 5
    assert data["success_count"] >= 2
    assert data["failed_count"] >= 1
    assert data["dead_letter_count"] >= 1
    assert data["replayed_original_count"] >= 1
    assert data["replay_success_count"] >= 1
    categories = data["error_category_counts"]
    assert categories.get("timeout", 0) >= 1
    assert categories.get("remote_server_error", 0) >= 1


async def test_control_scheduler_slo_includes_error_type_counts(client):
    now = datetime.now(UTC)
    session, agen = await _get_session()
    try:
        session.add(
            SchedulerJobRun(
                organization_id=1,
                job_name="job_ok",
                status="ok",
                started_at=now - timedelta(minutes=10),
                finished_at=now - timedelta(minutes=9),
                duration_ms=150,
            )
        )
        session.add(
            SchedulerJobRun(
                organization_id=1,
                job_name="job_err_1",
                status="error",
                started_at=now - timedelta(minutes=8),
                finished_at=now - timedelta(minutes=7),
                duration_ms=100,
                error="TimeoutError: sync timed out",
            )
        )
        session.add(
            SchedulerJobRun(
                organization_id=1,
                job_name="job_err_2",
                status="error",
                started_at=now - timedelta(minutes=6),
                finished_at=now - timedelta(minutes=5),
                duration_ms=100,
                error="ValueError: invalid payload",
            )
        )
        await session.commit()
    finally:
        await agen.aclose()

    resp = await client.get("/api/v1/control/scheduler/slo")
    assert resp.status_code == 200
    body = resp.json()
    assert "error_type_counts" in body
    assert body["error_type_counts"].get("TimeoutError", 0) >= 1
    assert body["error_type_counts"].get("ValueError", 0) >= 1
