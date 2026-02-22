from datetime import datetime, timezone

from app.core.security import create_access_token
from app.core.deps import get_db
from app.main import app as fastapi_app
from app.models.email import Email


def _auth_headers(user_id: int, email: str, role: str, org_id: int = 1) -> dict:
    token = create_access_token({"id": user_id, "email": email, "role": role, "org_id": org_id})
    return {"Authorization": f"Bearer {token}"}


async def test_ops_project_create_requires_manager_or_above(client):
    headers = _auth_headers(2, "staff@ai.com", "STAFF")
    response = await client.post(
        "/api/v1/ops/projects",
        json={"title": "Restricted Project"},
        headers=headers,
    )
    assert response.status_code == 403


async def test_ops_task_create_logs_event(client):
    headers = _auth_headers(1, "ceo@ai.com", "CEO")
    create_response = await client.post(
        "/api/v1/ops/tasks",
        json={"title": "Audit me"},
        headers=headers,
    )
    assert create_response.status_code == 201

    events_response = await client.get("/api/v1/ops/events", headers=headers)
    assert events_response.status_code == 200
    assert any(item["event_type"] == "task_created" for item in events_response.json())


async def test_approval_request_and_approve_flow(client):
    staff_headers = _auth_headers(3, "staff@ai.com", "STAFF")
    req = await client.post(
        "/api/v1/approvals/request",
        json={"approval_type": "assign_leads", "payload_json": {"count": 10}},
        headers=staff_headers,
    )
    assert req.status_code == 201
    approval_id = req.json()["id"]
    assert req.json()["status"] == "pending"

    ceo_headers = _auth_headers(1, "ceo@ai.com", "CEO")
    approved = await client.post(
        f"/api/v1/approvals/{approval_id}/approve",
        json={"note": "YES EXECUTE"},
        headers=ceo_headers,
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"


async def test_risky_approval_requires_yes_execute(client):
    staff_headers = _auth_headers(3, "staff@ai.com", "STAFF")
    req = await client.post(
        "/api/v1/approvals/request",
        json={"approval_type": "spend", "payload_json": {"amount": 50}},
        headers=staff_headers,
    )
    assert req.status_code == 201
    approval_id = req.json()["id"]

    ceo_headers = _auth_headers(1, "ceo@ai.com", "CEO")
    denied = await client.post(
        f"/api/v1/approvals/{approval_id}/approve",
        json={"note": "approved"},
        headers=ceo_headers,
    )
    assert denied.status_code == 400


async def test_approval_timeline_returns_summary_and_items(client):
    staff_headers = _auth_headers(3, "staff@ai.com", "STAFF")
    req = await client.post(
        "/api/v1/approvals/request",
        json={"approval_type": "assign_leads", "payload_json": {"count": 10}},
        headers=staff_headers,
    )
    assert req.status_code == 201

    ceo_headers = _auth_headers(1, "ceo@ai.com", "CEO")
    timeline = await client.get("/api/v1/approvals/timeline?limit=10", headers=ceo_headers)
    assert timeline.status_code == 200
    data = timeline.json()
    assert "pending_count" in data
    assert "approved_count" in data
    assert "rejected_count" in data
    assert isinstance(data["items"], list)
    assert data["items"]


async def _seed_email_for_org1() -> int:
    override = fastapi_app.dependency_overrides[get_db]
    agen = override()
    session = await agen.__anext__()
    try:
        email = Email(
            organization_id=1,
            gmail_id="test-gmail-id-ops-daily-run",
            thread_id="thread-1",
            from_address="lead@example.com",
            to_address="owner@example.com",
            subject="Need details about admissions",
            body_text="Hi, can you share details and next steps?",
            received_at=datetime.now(timezone.utc),
            is_read=False,
            reply_sent=False,
            created_at=datetime.now(timezone.utc),
        )
        session.add(email)
        await session.commit()
        await session.refresh(email)
        return email.id
    finally:
        await agen.aclose()


async def test_ops_daily_run_creates_drafts_only(client):
    ceo_headers = _auth_headers(1, "ceo@ai.com", "CEO")

    team_member = await client.post(
        "/api/v1/memory/team",
        json={
            "name": "Ravi",
            "role_title": "Backend Developer",
            "team": "tech",
            "skills": "FastAPI",
            "ai_level": 3,
            "current_project": "Clone API",
        },
        headers=ceo_headers,
    )
    assert team_member.status_code == 201

    await _seed_email_for_org1()

    daily_run = await client.post("/api/v1/ops/daily-run?draft_email_limit=1", headers=ceo_headers)
    assert daily_run.status_code == 200
    payload = daily_run.json()
    assert payload["status"] == "draft_only_completed"
    assert payload["requires_approval"] is True
    assert payload["drafted_plan_count"] >= 1
    assert payload["drafted_email_count"] >= 1

    inbox = await client.get("/api/v1/email/inbox?limit=10", headers=ceo_headers)
    assert inbox.status_code == 200
    drafted_items = [e for e in inbox.json() if e.get("draft_reply")]
    assert drafted_items
    assert all(not e["reply_sent"] for e in drafted_items)


async def test_ops_daily_run_staff_forbidden(client):
    staff_headers = _auth_headers(4, "staff@ai.com", "STAFF")
    response = await client.post("/api/v1/ops/daily-run", headers=staff_headers)
    assert response.status_code == 403


async def test_ops_daily_run_is_idempotent_same_scope_same_day(client):
    ceo_headers = _auth_headers(1, "ceo@ai.com", "CEO")
    team_member = await client.post(
        "/api/v1/memory/team",
        json={
            "name": "Anu",
            "role_title": "Ops Coordinator",
            "team": "ops",
            "skills": "Coordination",
            "ai_level": 2,
            "current_project": "Daily execution",
        },
        headers=ceo_headers,
    )
    assert team_member.status_code == 201
    await _seed_email_for_org1()

    first = await client.post("/api/v1/ops/daily-run?draft_email_limit=1", headers=ceo_headers)
    assert first.status_code == 200
    first_payload = first.json()
    assert first_payload["idempotent_reuse"] is False

    second = await client.post("/api/v1/ops/daily-run?draft_email_limit=1", headers=ceo_headers)
    assert second.status_code == 200
    second_payload = second.json()
    assert second_payload["status"] == "already_completed"
    assert second_payload["idempotent_reuse"] is True
    assert second_payload["daily_run_id"] == first_payload["daily_run_id"]


async def test_ops_daily_runs_history_lists_runs(client):
    ceo_headers = _auth_headers(1, "ceo@ai.com", "CEO")
    team_member = await client.post(
        "/api/v1/memory/team",
        json={
            "name": "Dev",
            "role_title": "Developer",
            "team": "tech",
            "skills": "Python",
            "ai_level": 3,
            "current_project": "API",
        },
        headers=ceo_headers,
    )
    assert team_member.status_code == 201

    created = await client.post("/api/v1/ops/daily-run?draft_email_limit=0", headers=ceo_headers)
    assert created.status_code == 200
    run_id = created.json()["daily_run_id"]

    history = await client.get("/api/v1/ops/daily-runs?limit=10", headers=ceo_headers)
    assert history.status_code == 200
    data = history.json()
    assert isinstance(data, list)
    assert any(item["id"] == run_id for item in data)
