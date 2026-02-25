"""Comprehensive tests for Ops Intelligence: signals, metrics, reports, decisions, policies."""
import json
from datetime import date, datetime, timedelta, timezone
from typing import cast

from sqlalchemy import func, select

from app.core.deps import get_db
from app.core.security import create_access_token
from app.main import app as fastapi_app
from app.models.employee import Employee
from app.models.integration_signal import IntegrationSignal
from app.models.organization import Organization
from app.models.user import User
from app.services import signal_ingestion
from app.services.metrics_service import _monday_of


def _auth(role: str = "CEO", org_id: int = 1) -> dict:
    identity_by_role = {
        "CEO": (1, "ceo@org1.com"),
        "ADMIN": (1, "ceo@org1.com"),
        "MANAGER": (3, "manager@org1.com"),
        "STAFF": (4, "staff@org1.com"),
    }
    user_id, email = identity_by_role.get(role, (1, "ceo@org1.com"))
    if org_id == 2:
        user_id, email = (2, "ceo@org2.com")
    token = create_access_token({"id": user_id, "email": email, "role": role, "org_id": org_id, "token_version": 1})
    return {"Authorization": f"Bearer {token}"}


async def _seed(org_id: int = 1) -> None:
    """Ensure org and user rows exist.  conftest already seeds org 1 / user 1,
    so we only insert when they are missing (e.g. org_id != 1)."""
    override = fastapi_app.dependency_overrides[get_db]
    agen = override()
    session = await agen.__anext__()
    try:
        if await session.get(Organization, org_id) is None:
            session.add(Organization(id=org_id, name=f"Org {org_id}", slug=f"org-{org_id}"))
            await session.flush()
        if await session.get(User, 1) is None:
            session.add(User(id=1, email="ceo@org1.com", name="CEO", role="CEO", organization_id=org_id, password_hash="x"))
        await session.commit()
    except Exception:
        await session.rollback()
    finally:
        await agen.aclose()


async def _seed_employee(org_id: int = 1, **kwargs) -> int:
    override = fastapi_app.dependency_overrides[get_db]
    agen = override()
    session = await agen.__anext__()
    try:
        emp = Employee(organization_id=org_id, **kwargs)
        session.add(emp)
        await session.commit()
        await session.refresh(emp)
        return cast(int, emp.id)
    finally:
        await agen.aclose()


async def _seed_signal(org_id: int, source: str, external_id: str, employee_id: int | None, payload: dict) -> None:
    override = fastapi_app.dependency_overrides[get_db]
    agen = override()
    session = await agen.__anext__()
    try:
        import hashlib
        payload_str = json.dumps(payload, sort_keys=True, default=str)
        sig = IntegrationSignal(
            organization_id=org_id,
            source=source,
            external_id=external_id,
            employee_id=employee_id,
            timestamp=datetime.now(timezone.utc),
            payload_json=payload_str,
            hash=hashlib.sha256(payload_str.encode()).hexdigest(),
        )
        session.add(sig)
        await session.commit()
    finally:
        await agen.aclose()


# ---- Signal Ingestion Tests ----

async def test_sync_clickup_not_connected(client):
    await _seed()
    resp = await client.post("/api/v1/ops/sync/clickup")
    assert resp.status_code == 200
    assert resp.json()["error"] == "ClickUp not connected"


async def test_sync_github_not_connected(client):
    await _seed()
    resp = await client.post("/api/v1/ops/sync/github")
    assert resp.status_code == 200
    assert resp.json()["error"] == "GitHub not connected"


async def test_sync_gmail_not_connected(client):
    await _seed()
    resp = await client.post("/api/v1/ops/sync/gmail")
    assert resp.status_code == 200
    assert resp.json()["error"] == "Gmail not connected"


async def test_sync_endpoints_require_admin(client):
    staff_headers = _auth(role="STAFF")
    for endpoint in ["/api/v1/ops/sync/clickup", "/api/v1/ops/sync/github", "/api/v1/ops/sync/gmail"]:
        resp = await client.post(endpoint, headers=staff_headers)
        assert resp.status_code == 403, f"{endpoint} should require admin"


async def test_sanitize_payload_removes_tokens():
    payload = {
        "name": "Task 1",
        "access_token": "secret123",
        "nested": {"refresh_token": "abc", "data": "keep"},
    }
    sanitized = signal_ingestion._sanitize_payload(payload)
    assert "access_token" not in sanitized
    assert sanitized["name"] == "Task 1"
    assert "refresh_token" not in sanitized["nested"]
    assert sanitized["nested"]["data"] == "keep"


async def test_gmail_domain_filter(monkeypatch):
    """Verify work email domain allowlist is respected."""
    monkeypatch.setattr(signal_ingestion.settings, "WORK_EMAIL_DOMAINS", "work.com,empire.com")
    domains = signal_ingestion._work_email_domains()
    assert "work.com" in domains
    assert "empire.com" in domains
    assert len(domains) == 2


# ---- Metrics Computation Tests ----

async def test_compute_metrics_no_employees(client):
    await _seed()
    resp = await client.post("/api/v1/ops/compute/weekly-metrics?weeks=1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["employees_processed"] == 0


async def test_compute_metrics_with_signals(client):
    await _seed()
    emp_id = await _seed_employee(
        org_id=1, name="Alice", email="alice@test.com", github_username="alice-gh",
        clickup_user_id="cu_1",
    )

    # Add a ClickUp signal for this week
    monday = _monday_of(date.today())
    await _seed_signal(1, "clickup", "task:1001", emp_id, {
        "name": "Build feature",
        "status": "complete",
        "priority": 3,
        "due_date": str(monday + timedelta(days=5)),
    })
    # Add a GitHub signal
    await _seed_signal(1, "github", "pr:org/repo#42", emp_id, {
        "title": "Add login",
        "state": "closed",
        "merged": True,
        "changed_files": 5,
        "review_comments": 2,
    })

    resp = await client.post("/api/v1/ops/compute/weekly-metrics?weeks=1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["employees_processed"] >= 1
    assert body["task_metrics"] >= 1
    assert body["code_metrics"] >= 1


async def test_compute_metrics_requires_admin(client):
    resp = await client.post(
        "/api/v1/ops/compute/weekly-metrics?weeks=1",
        headers=_auth(role="STAFF"),
    )
    assert resp.status_code == 403


# ---- Weekly Reports Tests ----

async def test_generate_team_health_report(client):
    await _seed()
    await _seed_employee(org_id=1, name="Bob", email="bob@test.com")

    monday = _monday_of(date.today())
    resp = await client.post(
        f"/api/v1/ops/reports/weekly?week_start={monday.isoformat()}&report_type=team_health",
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["report_type"] == "team_health"
    assert "Team Health Report" in body["content_markdown"]
    assert "Bob" in body["content_markdown"]


async def test_generate_project_risk_report(client):
    await _seed()
    monday = _monday_of(date.today())
    resp = await client.post(
        f"/api/v1/ops/reports/weekly?week_start={monday.isoformat()}&report_type=project_risk",
    )
    assert resp.status_code == 201
    assert "Project Risk Report" in resp.json()["content_markdown"]


async def test_generate_founder_review_report(client):
    await _seed()
    monday = _monday_of(date.today())
    resp = await client.post(
        f"/api/v1/ops/reports/weekly?week_start={monday.isoformat()}&report_type=founder_review",
    )
    assert resp.status_code == 201
    assert "Founder Decision Review" in resp.json()["content_markdown"]


async def test_get_report_returns_none_when_missing(client):
    await _seed()
    resp = await client.get("/api/v1/ops/reports/weekly?week_start=2026-01-05&report_type=team_health")
    assert resp.status_code == 200
    assert resp.json() is None


async def test_report_invalid_type_rejected(client):
    resp = await client.post("/api/v1/ops/reports/weekly?week_start=2026-01-05&report_type=invalid")
    assert resp.status_code == 422


# ---- Decision Log Tests ----

async def test_create_decision_log(client):
    await _seed()
    resp = await client.post("/api/v1/ops/decision-log", json={
        "decision_type": "approve",
        "context": "Employee requested budget for new tools",
        "objective": "Improve developer productivity",
        "constraints": "Budget limit $500/month",
        "deadline": "2026-03-01",
        "success_metric": "20% faster feature delivery",
        "reason": "Data shows productivity gap vs industry benchmark",
        "risk": "Low - reversible if tools underperform",
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["decision_type"] == "approve"
    assert body["created_by"] == 1


async def test_list_decision_log(client):
    await _seed()
    # Create 3 decisions
    for dtype in ["approve", "reject", "defer"]:
        await client.post("/api/v1/ops/decision-log", json={
            "decision_type": dtype,
            "context": f"Test context for {dtype}",
            "objective": "Test objective",
            "reason": "Test reason",
        })

    resp = await client.get("/api/v1/ops/decision-log")
    assert resp.status_code == 200
    assert len(resp.json()) == 3


async def test_decision_log_requires_admin(client):
    resp = await client.post(
        "/api/v1/ops/decision-log",
        json={"decision_type": "approve", "context": "x", "objective": "y", "reason": "z"},
        headers=_auth(role="STAFF"),
    )
    assert resp.status_code == 403


# ---- Policy Engine Tests ----

async def test_generate_policies_no_decisions(client):
    await _seed()
    resp = await client.post("/api/v1/ops/policy/generate")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_generate_policies_from_decisions(client):
    await _seed()
    # Create 3 approvals to trigger pattern
    for i in range(3):
        await client.post("/api/v1/ops/decision-log", json={
            "decision_type": "approve",
            "context": f"Budget request #{i}",
            "objective": "Productivity",
            "reason": "Data-backed",
        })

    resp = await client.post("/api/v1/ops/policy/generate")
    assert resp.status_code == 200
    drafts = resp.json()
    assert len(drafts) >= 1
    assert all(d["is_active"] is False for d in drafts)


async def test_activate_policy(client):
    await _seed()
    # Create decisions and generate drafts
    for i in range(3):
        await client.post("/api/v1/ops/decision-log", json={
            "decision_type": "approve", "context": f"Request #{i}",
            "objective": "Test", "reason": "Reason",
        })
    gen_resp = await client.post("/api/v1/ops/policy/generate")
    policy_id = gen_resp.json()[0]["id"]

    # Activate
    resp = await client.post(f"/api/v1/ops/policy/activate/{policy_id}")
    assert resp.status_code == 200
    assert resp.json()["is_active"] is True


async def test_list_policies(client):
    await _seed()
    resp = await client.get("/api/v1/ops/policies")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_policy_activate_not_found(client):
    await _seed()
    resp = await client.post("/api/v1/ops/policy/activate/999")
    assert resp.status_code == 404


# ---- CI/CD Signal Ingestion Tests ----

async def test_sync_github_cicd_not_connected(client):
    await _seed()
    resp = await client.post("/api/v1/ops/sync/github-cicd")
    assert resp.status_code == 200
    body = resp.json()
    assert body["error"] == "GitHub not connected"
    assert body["workflow_runs"] == 0
    assert body["deployments"] == 0


async def test_sync_github_cicd_requires_admin(client):
    resp = await client.post(
        "/api/v1/ops/sync/github-cicd",
        headers=_auth(role="STAFF"),
    )
    assert resp.status_code == 403


async def test_sync_github_cicd_with_data(client, monkeypatch):
    """Full end-to-end: mock GitHub API, ingest workflow runs + deployments."""
    await _seed()
    await _seed_employee(
        org_id=1, name="Dev", email="dev@test.com", github_username="dev-user",
    )

    # Seed a connected GitHub integration
    override = fastapi_app.dependency_overrides[get_db]
    agen = override()
    session = await agen.__anext__()
    try:
        from app.models.integration import Integration
        integ = Integration(
            organization_id=1, type="github", status="connected",
            config_json={"access_token": "ghp_fake"},
        )
        session.add(integ)
        await session.commit()
    finally:
        await agen.aclose()

    # Mock GitHub API calls
    async def fake_list_repos(token):
        return [{"owner": {"login": "myorg"}, "name": "myrepo"}]

    async def fake_get_workflow_runs(token, owner, repo, per_page=15):
        return [
            {
                "id": 100,
                "name": "CI",
                "status": "completed",
                "conclusion": "success",
                "head_branch": "main",
                "actor": {"login": "dev-user"},
                "event": "push",
                "run_number": 42,
                "run_attempt": 1,
                "run_started_at": "2026-02-24T10:00:00Z",
                "updated_at": "2026-02-24T10:05:30Z",
                "created_at": "2026-02-24T10:00:00Z",
            },
            {
                "id": 101,
                "name": "Deploy",
                "status": "completed",
                "conclusion": "failure",
                "head_branch": "feature-x",
                "actor": {"login": "unknown-user"},
                "event": "pull_request",
                "run_number": 43,
                "run_attempt": 1,
                "updated_at": "2026-02-24T11:00:00Z",
                "created_at": "2026-02-24T11:00:00Z",
            },
        ]

    async def fake_get_deployments(token, owner, repo, per_page=10):
        return [
            {
                "id": 200,
                "environment": "production",
                "ref": "main",
                "task": "deploy",
                "creator": {"login": "dev-user"},
                "description": "Deploy v1.2.0",
                "updated_at": "2026-02-24T12:00:00Z",
                "created_at": "2026-02-24T12:00:00Z",
            },
        ]

    from app.tools import github as github_tool
    monkeypatch.setattr(github_tool, "list_repos", fake_list_repos)
    monkeypatch.setattr(github_tool, "get_workflow_runs", fake_get_workflow_runs)
    monkeypatch.setattr(github_tool, "get_deployments", fake_get_deployments)

    resp = await client.post("/api/v1/ops/sync/github-cicd")
    assert resp.status_code == 200
    body = resp.json()
    assert body["workflow_runs"] == 2
    assert body["deployments"] == 1
    assert body["error"] is None


async def test_sync_github_cicd_calculates_duration(client, monkeypatch):
    """Verify duration_seconds is calculated for completed runs."""
    await _seed()

    override = fastapi_app.dependency_overrides[get_db]
    agen = override()
    session = await agen.__anext__()
    try:
        from app.models.integration import Integration
        integ = Integration(
            organization_id=1, type="github", status="connected",
            config_json={"access_token": "ghp_fake"},
        )
        session.add(integ)
        await session.commit()
    finally:
        await agen.aclose()

    async def fake_list_repos(token):
        return [{"owner": {"login": "org"}, "name": "repo"}]

    async def fake_get_workflow_runs(token, owner, repo, per_page=15):
        return [{
            "id": 300,
            "name": "Build",
            "status": "completed",
            "conclusion": "success",
            "head_branch": "main",
            "actor": {"login": ""},
            "event": "push",
            "run_number": 1,
            "run_attempt": 1,
            "run_started_at": "2026-02-24T10:00:00Z",
            "updated_at": "2026-02-24T10:02:30Z",
            "created_at": "2026-02-24T10:00:00Z",
        }]

    async def fake_get_deployments(token, owner, repo, per_page=10):
        return []

    from app.tools import github as github_tool
    monkeypatch.setattr(github_tool, "list_repos", fake_list_repos)
    monkeypatch.setattr(github_tool, "get_workflow_runs", fake_get_workflow_runs)
    monkeypatch.setattr(github_tool, "get_deployments", fake_get_deployments)

    resp = await client.post("/api/v1/ops/sync/github-cicd")
    assert resp.status_code == 200
    assert resp.json()["workflow_runs"] == 1

    # Verify the stored signal has duration
    agen2 = override()
    session2 = await agen2.__anext__()
    try:
        result = await session2.execute(
            select(IntegrationSignal).where(
                IntegrationSignal.source == "github_workflow",
            )
        )
        sig = result.scalar_one()
        payload = json.loads(sig.payload_json)
        assert payload["duration_seconds"] == 150  # 2m30s
        assert payload["conclusion"] == "success"
    finally:
        await agen2.aclose()


async def test_sync_github_cicd_dedup_on_rerun(client, monkeypatch):
    """Running sync twice should not duplicate signals."""
    await _seed()

    override = fastapi_app.dependency_overrides[get_db]
    agen = override()
    session = await agen.__anext__()
    try:
        from app.models.integration import Integration
        integ = Integration(
            organization_id=1, type="github", status="connected",
            config_json={"access_token": "ghp_fake"},
        )
        session.add(integ)
        await session.commit()
    finally:
        await agen.aclose()

    async def fake_list_repos(token):
        return [{"owner": {"login": "org"}, "name": "repo"}]

    async def fake_get_workflow_runs(token, owner, repo, per_page=15):
        return [{
            "id": 400, "name": "CI", "status": "completed", "conclusion": "success",
            "head_branch": "main", "actor": {"login": ""}, "event": "push",
            "run_number": 1, "run_attempt": 1,
            "updated_at": "2026-02-24T10:00:00Z", "created_at": "2026-02-24T10:00:00Z",
        }]

    async def fake_get_deployments(token, owner, repo, per_page=10):
        return []

    from app.tools import github as github_tool
    monkeypatch.setattr(github_tool, "list_repos", fake_list_repos)
    monkeypatch.setattr(github_tool, "get_workflow_runs", fake_get_workflow_runs)
    monkeypatch.setattr(github_tool, "get_deployments", fake_get_deployments)

    # Run twice
    resp1 = await client.post("/api/v1/ops/sync/github-cicd")
    assert resp1.json()["workflow_runs"] == 1
    resp2 = await client.post("/api/v1/ops/sync/github-cicd")
    assert resp2.json()["workflow_runs"] == 1

    # Should still be only 1 signal row
    agen2 = override()
    session2 = await agen2.__anext__()
    try:
        result = await session2.execute(
            select(func.count()).select_from(IntegrationSignal).where(
                IntegrationSignal.source == "github_workflow",
            )
        )
        assert result.scalar() == 1
    finally:
        await agen2.aclose()
