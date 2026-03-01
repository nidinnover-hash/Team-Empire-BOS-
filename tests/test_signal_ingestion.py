"""
Tests for app/services/signal_ingestion.py

Covers:
  - ClickUp, GitHub, Gmail, GitHub CI/CD signal ingestion
  - No-integration (disconnected) paths
  - API error handling
  - Idempotency (no duplicate signals on re-run)
  - Employee mapping by email / github_username / clickup_user_id
  - get_ingestion_stats()
  - Payload sanitization (secrets stripped)
"""
from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import select

from app.models.employee import Employee
from app.models.integration import Integration
from app.models.integration_signal import IntegrationSignal
from app.services import signal_ingestion as sig_mod
from app.services.signal_ingestion import (
    _sanitize_payload,
    get_ingestion_stats,
    ingest_clickup_signals,
    ingest_github_cicd_signals,
    ingest_github_signals,
    ingest_gmail_signals,
)


# ---------------------------------------------------------------------------
# Helpers — seed data factories
# ---------------------------------------------------------------------------


async def _add_integration(
    db, org_id: int, itype: str, config: dict, status: str = "connected"
) -> Integration:
    """Insert an Integration row and return it."""
    integ = Integration(
        organization_id=org_id,
        type=itype,
        config_json=config,
        status=status,
    )
    db.add(integ)
    await db.commit()
    await db.refresh(integ)
    return integ


async def _add_employee(
    db,
    org_id: int,
    name: str,
    email: str,
    *,
    github_username: str | None = None,
    clickup_user_id: str | None = None,
) -> Employee:
    emp = Employee(
        organization_id=org_id,
        name=name,
        email=email,
        github_username=github_username,
        clickup_user_id=clickup_user_id,
        is_active=True,
    )
    db.add(emp)
    await db.commit()
    await db.refresh(emp)
    return emp


async def _count_signals(db, org_id: int, source: str | None = None) -> int:
    stmt = select(IntegrationSignal).where(
        IntegrationSignal.organization_id == org_id
    )
    if source:
        stmt = stmt.where(IntegrationSignal.source == source)
    result = await db.execute(stmt)
    return len(result.scalars().all())


async def _get_signals(db, org_id: int, source: str) -> list[IntegrationSignal]:
    result = await db.execute(
        select(IntegrationSignal).where(
            IntegrationSignal.organization_id == org_id,
            IntegrationSignal.source == source,
        )
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Fixture: reset module-level ingestion stats between tests
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_ingestion_stats():
    """Reset the module-level stats counters so tests are isolated."""
    saved = dict(sig_mod._ingestion_stats)
    for k in sig_mod._ingestion_stats:
        sig_mod._ingestion_stats[k] = 0
    yield
    sig_mod._ingestion_stats.update(saved)


# ---------------------------------------------------------------------------
# 1. ingest_clickup_signals — no integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clickup_no_integration(db, monkeypatch):
    """When there is no ClickUp integration, returns synced=0 with error."""
    result = await ingest_clickup_signals(db, org_id=1)
    assert result["synced"] == 0
    assert "not connected" in result["error"].lower()


# ---------------------------------------------------------------------------
# 2. ingest_clickup_signals — success
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clickup_success(db, monkeypatch):
    """ClickUp ingestion creates IntegrationSignal rows from tasks."""
    await _add_integration(db, 1, "clickup", {"access_token": "tok", "team_id": "T1"})

    fake_tasks = [
        {
            "id": "abc1",
            "name": "Fix homepage",
            "status": {"status": "in progress"},
            "priority": {"id": "2"},
            "due_date": None,
            "date_updated": "1700000000000",
            "assignees": [{"id": "999", "username": "dev1"}],
            "tags": [{"name": "bug"}],
            "list": {"name": "Sprint 12"},
        },
        {
            "id": "abc2",
            "name": "Deploy v2",
            "status": "done",
            "priority": None,
            "due_date": "1700100000000",
            "date_created": "1699900000000",
            "assignees": [],
            "tags": [],
            "list": None,
        },
    ]

    async def fake_get_tasks(api_token, team_id, include_closed=False):
        assert api_token == "tok"
        assert team_id == "T1"
        return fake_tasks

    # The tools are lazily imported inside the function body, so monkeypatch
    # on the actual tool module, not on signal_ingestion.
    from app.tools import clickup as clickup_mod

    monkeypatch.setattr(clickup_mod, "get_tasks", fake_get_tasks)
    monkeypatch.setattr(clickup_mod, "parse_priority", lambda t: 3)
    monkeypatch.setattr(clickup_mod, "parse_due_date", lambda t: None)

    result = await ingest_clickup_signals(db, org_id=1)
    assert result["synced"] == 2
    assert result["error"] is None

    count = await _count_signals(db, 1, "clickup")
    assert count == 2

    signals = await _get_signals(db, 1, "clickup")
    ext_ids = {s.external_id for s in signals}
    assert "task:abc1" in ext_ids
    assert "task:abc2" in ext_ids

    # Verify payload does not contain access_token
    for sig in signals:
        payload = json.loads(sig.payload_json)
        assert "access_token" not in payload


# ---------------------------------------------------------------------------
# 3. ingest_clickup_signals — API error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clickup_api_error(db, monkeypatch):
    """ClickUp ingestion handles httpx errors gracefully."""
    await _add_integration(db, 1, "clickup", {"access_token": "tok", "team_id": "T1"})

    async def fake_get_tasks(*args, **kwargs):
        raise httpx.ConnectError("connection refused")

    from app.tools import clickup as clickup_mod

    monkeypatch.setattr(clickup_mod, "get_tasks", fake_get_tasks)

    result = await ingest_clickup_signals(db, org_id=1)
    assert result["synced"] == 0
    assert result["error"]  # non-empty error string
    assert "ConnectError" in result["error"]


# ---------------------------------------------------------------------------
# 4. ingest_github_signals — no integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_github_no_integration(db, monkeypatch):
    """When there is no GitHub integration, returns synced=0 with error."""
    result = await ingest_github_signals(db, org_id=1)
    assert result["synced"] == 0
    assert "not connected" in result["error"].lower()


# ---------------------------------------------------------------------------
# 5. ingest_github_signals — success
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_github_success(db, monkeypatch):
    """GitHub ingestion creates signals from PRs and issues."""
    await _add_integration(db, 1, "github", {"access_token": "ghp_fake"})

    fake_repos = [
        {"owner": {"login": "myorg"}, "name": "backend"},
    ]
    fake_prs = [
        {
            "number": 42,
            "title": "Add auth",
            "state": "open",
            "user": {"login": "DevUser"},
            "updated_at": "2026-02-01T12:00:00Z",
            "merged_at": None,
            "additions": 100,
            "deletions": 20,
            "changed_files": 5,
            "review_comments": 3,
        },
    ]
    fake_issues = [
        {
            "number": 7,
            "title": "Login broken",
            "state": "open",
            "user": {"login": "reporter"},
            "updated_at": "2026-02-02T08:00:00Z",
            "labels": [{"name": "bug"}, {"name": "p1"}],
        },
    ]

    async def fake_list_repos(token):
        return fake_repos

    async def fake_get_prs(token, owner, repo, state="all", per_page=30):
        return fake_prs

    async def fake_get_issues(token, owner, repo, state="all", per_page=30):
        return fake_issues

    from app.tools import github as github_mod

    monkeypatch.setattr(github_mod, "list_repos", fake_list_repos)
    monkeypatch.setattr(github_mod, "get_pull_requests", fake_get_prs)
    monkeypatch.setattr(github_mod, "get_issues", fake_get_issues)

    result = await ingest_github_signals(db, org_id=1)
    assert result["synced"] == 2  # 1 PR + 1 issue
    assert result["error"] is None

    signals = await _get_signals(db, 1, "github")
    ext_ids = {s.external_id for s in signals}
    assert "pr:myorg/backend#42" in ext_ids
    assert "issue:myorg/backend#7" in ext_ids


# ---------------------------------------------------------------------------
# 6. ingest_github_signals — empty repos
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_github_empty_repos(db, monkeypatch):
    """When list_repos returns empty, synced=0 with no error."""
    await _add_integration(db, 1, "github", {"access_token": "ghp_fake"})

    async def fake_list_repos(token):
        return []

    from app.tools import github as github_mod

    monkeypatch.setattr(github_mod, "list_repos", fake_list_repos)

    result = await ingest_github_signals(db, org_id=1)
    assert result["synced"] == 0
    assert result["error"] is None


# ---------------------------------------------------------------------------
# 7. ingest_gmail_signals — no integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gmail_no_integration(db, monkeypatch):
    """When there is no Gmail integration, returns synced=0 with error."""
    result = await ingest_gmail_signals(db, org_id=1)
    assert result["synced"] == 0
    assert "not connected" in result["error"].lower()


# ---------------------------------------------------------------------------
# 8. ingest_gmail_signals — success
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gmail_success(db, monkeypatch):
    """Gmail ingestion creates IntegrationSignal rows from email metadata."""
    await _add_integration(
        db,
        1,
        "gmail",
        {"access_token": "ya29_fake", "refresh_token": "rt_fake", "expires_at": 9999999999},
    )

    fake_emails = [
        {
            "gmail_id": "msg001",
            "from_address": "boss@empire.com",
            "to_address": "me@empire.com",
            "subject": "Q1 Review",
            "thread_id": "thread_001",
            "snippet": "Let's discuss the quarter...",
            "received_at": "2026-02-15T10:00:00+00:00",
            "labelIds": ["INBOX"],
        },
        {
            "gmail_id": "msg002",
            "from_address": "vendor@acme.com",
            "to_address": "me@empire.com",
            "subject": "Invoice #123",
            "thread_id": "thread_002",
            "snippet": "Attached invoice",
            "received_at": "2026-02-16T14:00:00+00:00",
            "labelIds": ["INBOX"],
        },
    ]

    def fake_fetch_emails(access_token, refresh_token, expires_at, max_results=50):
        return fake_emails, False  # (emails, refreshed)

    from app.tools import gmail as gmail_mod

    monkeypatch.setattr(gmail_mod, "fetch_recent_emails", fake_fetch_emails)
    # Ensure no domain filtering (allow all)
    from app.core.config import settings

    monkeypatch.setattr(settings, "WORK_EMAIL_DOMAINS", "")

    result = await ingest_gmail_signals(db, org_id=1)
    assert result["synced"] == 2
    assert result["error"] is None

    signals = await _get_signals(db, 1, "gmail")
    ext_ids = {s.external_id for s in signals}
    assert "msg:msg001" in ext_ids
    assert "msg:msg002" in ext_ids

    # Verify payload has subject but no body
    for sig in signals:
        payload = json.loads(sig.payload_json)
        assert "subject" in payload
        assert "body" not in payload
        # Tokens must be stripped
        assert "access_token" not in payload
        assert "refresh_token" not in payload


# ---------------------------------------------------------------------------
# 9. ingest_github_cicd_signals — success
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_github_cicd_success(db, monkeypatch):
    """GitHub CI/CD ingestion stores workflow runs and deployments."""
    await _add_integration(db, 1, "github", {"access_token": "ghp_fake"})

    fake_repos = [{"owner": {"login": "myorg"}, "name": "api"}]
    fake_runs = [
        {
            "id": 9001,
            "name": "CI",
            "status": "completed",
            "conclusion": "success",
            "head_branch": "main",
            "actor": {"login": "cibot"},
            "event": "push",
            "run_number": 55,
            "run_attempt": 1,
            "run_started_at": "2026-02-20T10:00:00Z",
            "updated_at": "2026-02-20T10:05:00Z",
            "created_at": "2026-02-20T10:00:00Z",
        },
    ]
    fake_deployments = [
        {
            "id": 8001,
            "environment": "production",
            "ref": "v2.1.0",
            "task": "deploy",
            "creator": {"login": "releasebot"},
            "description": "Production release v2.1.0",
            "updated_at": "2026-02-21T18:00:00Z",
            "created_at": "2026-02-21T17:55:00Z",
        },
    ]

    async def fake_list_repos(token):
        return fake_repos

    async def fake_get_wf_runs(token, owner, repo, per_page=15):
        return fake_runs

    async def fake_get_deploys(token, owner, repo, per_page=10):
        return fake_deployments

    from app.tools import github as github_mod

    monkeypatch.setattr(github_mod, "list_repos", fake_list_repos)
    monkeypatch.setattr(github_mod, "get_workflow_runs", fake_get_wf_runs)
    monkeypatch.setattr(github_mod, "get_deployments", fake_get_deploys)

    result = await ingest_github_cicd_signals(db, org_id=1)
    assert result["workflow_runs"] == 1
    assert result["deployments"] == 1
    assert result["error"] is None

    wf_signals = await _get_signals(db, 1, "github_workflow")
    assert len(wf_signals) == 1
    wf_payload = json.loads(wf_signals[0].payload_json)
    assert wf_payload["conclusion"] == "success"
    assert wf_payload["duration_seconds"] == 300  # 5 minutes

    deploy_signals = await _get_signals(db, 1, "github_deployment")
    assert len(deploy_signals) == 1
    dp_payload = json.loads(deploy_signals[0].payload_json)
    assert dp_payload["environment"] == "production"


# ---------------------------------------------------------------------------
# 10. get_ingestion_stats — returns counter dict
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_ingestion_stats(db, monkeypatch):
    """get_ingestion_stats returns current counters as a dict copy."""
    # Stats were reset by the autouse fixture
    stats = get_ingestion_stats()
    assert isinstance(stats, dict)
    assert "clickup_synced" in stats
    assert "github_synced" in stats
    assert "gmail_synced" in stats
    assert "github_cicd_synced" in stats

    # Mutating the returned dict must not affect the module state
    stats["clickup_synced"] = 999
    assert get_ingestion_stats()["clickup_synced"] == 0

    # Now run ingestion and verify stats increment
    await _add_integration(db, 1, "clickup", {"access_token": "tok", "team_id": "T1"})

    async def fake_get_tasks(api_token, team_id, include_closed=False):
        return [{"id": "t1", "name": "X", "status": "open", "date_created": "1700000000000", "assignees": [], "tags": []}]

    from app.tools import clickup as clickup_mod

    monkeypatch.setattr(clickup_mod, "get_tasks", fake_get_tasks)
    monkeypatch.setattr(clickup_mod, "parse_priority", lambda t: 2)
    monkeypatch.setattr(clickup_mod, "parse_due_date", lambda t: None)

    await ingest_clickup_signals(db, org_id=1)
    assert get_ingestion_stats()["clickup_synced"] == 1


# ---------------------------------------------------------------------------
# 11. Idempotency — no duplicate signals on re-run
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_idempotency_no_duplicates(db, monkeypatch):
    """Running ingestion twice with the same data must not create duplicates."""
    await _add_integration(db, 1, "github", {"access_token": "ghp_fake"})

    fake_repos = [{"owner": {"login": "org"}, "name": "repo"}]
    fake_prs = [
        {
            "number": 1,
            "title": "Init",
            "state": "merged",
            "user": {"login": "dev"},
            "updated_at": "2026-01-01T00:00:00Z",
            "merged_at": "2026-01-01T00:00:00Z",
            "additions": 10,
            "deletions": 0,
            "changed_files": 1,
            "review_comments": 0,
        },
    ]

    async def fake_list_repos(token):
        return fake_repos

    async def fake_get_prs(token, owner, repo, state="all", per_page=30):
        return fake_prs

    async def fake_get_issues(token, owner, repo, state="all", per_page=30):
        return []

    from app.tools import github as github_mod

    monkeypatch.setattr(github_mod, "list_repos", fake_list_repos)
    monkeypatch.setattr(github_mod, "get_pull_requests", fake_get_prs)
    monkeypatch.setattr(github_mod, "get_issues", fake_get_issues)

    # First run
    r1 = await ingest_github_signals(db, org_id=1)
    assert r1["synced"] == 1

    # Second run with same data
    r2 = await ingest_github_signals(db, org_id=1)
    assert r2["synced"] == 1  # still reports count of items processed

    # But only 1 row in DB (upsert, not insert)
    count = await _count_signals(db, 1, "github")
    assert count == 1


# ---------------------------------------------------------------------------
# 12. Employee mapping — link signals to employees
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_employee_mapping_clickup(db, monkeypatch):
    """ClickUp signals are linked to employees via clickup_user_id."""
    await _add_integration(db, 1, "clickup", {"access_token": "tok", "team_id": "T1"})
    emp = await _add_employee(
        db, 1, "Dev One", "dev@empire.com", clickup_user_id="CU_42"
    )

    fake_tasks = [
        {
            "id": "task1",
            "name": "Linked task",
            "status": {"status": "open"},
            "date_updated": "1700000000000",
            "assignees": [{"id": "CU_42", "username": "dev1"}],
            "tags": [],
            "list": None,
        },
    ]

    async def fake_get_tasks(api_token, team_id, include_closed=False):
        return fake_tasks

    from app.tools import clickup as clickup_mod

    monkeypatch.setattr(clickup_mod, "get_tasks", fake_get_tasks)
    monkeypatch.setattr(clickup_mod, "parse_priority", lambda t: 2)
    monkeypatch.setattr(clickup_mod, "parse_due_date", lambda t: None)

    await ingest_clickup_signals(db, org_id=1)

    signals = await _get_signals(db, 1, "clickup")
    assert len(signals) == 1
    assert signals[0].employee_id == emp.id


@pytest.mark.asyncio
async def test_employee_mapping_github(db, monkeypatch):
    """GitHub signals are linked to employees via github_username."""
    await _add_integration(db, 1, "github", {"access_token": "ghp_fake"})
    emp = await _add_employee(
        db, 1, "GH Dev", "ghdev@empire.com", github_username="ghdev"
    )

    async def fake_list_repos(token):
        return [{"owner": {"login": "org"}, "name": "repo"}]

    async def fake_get_prs(token, owner, repo, state="all", per_page=30):
        return [
            {
                "number": 10,
                "title": "PR by GH Dev",
                "state": "open",
                "user": {"login": "GHDev"},  # mixed case — mapping is lowercase
                "updated_at": "2026-02-10T00:00:00Z",
                "merged_at": None,
                "additions": 5,
                "deletions": 2,
                "changed_files": 1,
                "review_comments": 0,
            },
        ]

    async def fake_get_issues(token, owner, repo, state="all", per_page=30):
        return []

    from app.tools import github as github_mod

    monkeypatch.setattr(github_mod, "list_repos", fake_list_repos)
    monkeypatch.setattr(github_mod, "get_pull_requests", fake_get_prs)
    monkeypatch.setattr(github_mod, "get_issues", fake_get_issues)

    await ingest_github_signals(db, org_id=1)

    signals = await _get_signals(db, 1, "github")
    assert len(signals) == 1
    assert signals[0].employee_id == emp.id


@pytest.mark.asyncio
async def test_employee_mapping_gmail(db, monkeypatch):
    """Gmail signals are linked to employees via sender email."""
    await _add_integration(
        db, 1, "gmail",
        {"access_token": "ya29_fake", "refresh_token": "rt", "expires_at": 9999999999},
    )
    emp = await _add_employee(db, 1, "Boss", "boss@empire.com")

    fake_emails = [
        {
            "gmail_id": "m1",
            "from_address": "boss@empire.com",
            "to_address": "me@empire.com",
            "subject": "Update",
            "thread_id": "th1",
            "snippet": "...",
            "received_at": "2026-02-20T12:00:00+00:00",
        },
    ]

    def fake_fetch_emails(access_token, refresh_token, expires_at, max_results=50):
        return fake_emails, False

    from app.tools import gmail as gmail_mod
    from app.core.config import settings

    monkeypatch.setattr(gmail_mod, "fetch_recent_emails", fake_fetch_emails)
    monkeypatch.setattr(settings, "WORK_EMAIL_DOMAINS", "")

    await ingest_gmail_signals(db, org_id=1)

    signals = await _get_signals(db, 1, "gmail")
    assert len(signals) == 1
    assert signals[0].employee_id == emp.id


# ---------------------------------------------------------------------------
# 13. Gmail domain filter — non-work emails skipped
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gmail_domain_filter(db, monkeypatch):
    """When WORK_EMAIL_DOMAINS is set, emails from outside those domains are skipped."""
    await _add_integration(
        db, 1, "gmail",
        {"access_token": "ya29_fake", "refresh_token": "rt", "expires_at": 9999999999},
    )

    fake_emails = [
        {
            "gmail_id": "work1",
            "from_address": "alice@empire.com",
            "subject": "Work email",
            "received_at": "2026-02-20T12:00:00+00:00",
        },
        {
            "gmail_id": "personal1",
            "from_address": "spam@random.io",
            "subject": "Not work",
            "received_at": "2026-02-20T13:00:00+00:00",
        },
    ]

    def fake_fetch_emails(access_token, refresh_token, expires_at, max_results=50):
        return fake_emails, False

    from app.tools import gmail as gmail_mod
    from app.core.config import settings

    monkeypatch.setattr(gmail_mod, "fetch_recent_emails", fake_fetch_emails)
    monkeypatch.setattr(settings, "WORK_EMAIL_DOMAINS", "empire.com")

    result = await ingest_gmail_signals(db, org_id=1)
    assert result["synced"] == 1
    assert result["skipped_non_work"] == 1

    count = await _count_signals(db, 1, "gmail")
    assert count == 1


# ---------------------------------------------------------------------------
# 14. Payload sanitization — tokens stripped from stored payload
# ---------------------------------------------------------------------------


def test_sanitize_payload_removes_secrets():
    """_sanitize_payload strips sensitive keys from nested dicts."""
    raw = {
        "name": "test task",
        "access_token": "secret123",
        "nested": {
            "api_key": "key456",
            "safe_field": "visible",
        },
        "password": "hunter2",
        "status": "open",
    }
    sanitized = _sanitize_payload(raw)
    assert "access_token" not in sanitized
    assert "password" not in sanitized
    assert "api_key" not in sanitized.get("nested", {})
    assert sanitized["name"] == "test task"
    assert sanitized["status"] == "open"
    assert sanitized["nested"]["safe_field"] == "visible"


# ---------------------------------------------------------------------------
# 15. Upsert updates payload hash on change
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upsert_updates_on_payload_change(db, monkeypatch):
    """When the same signal is ingested with a changed payload, the hash and payload update."""
    await _add_integration(db, 1, "github", {"access_token": "ghp_fake"})

    call_count = 0

    async def fake_list_repos(token):
        return [{"owner": {"login": "org"}, "name": "repo"}]

    async def fake_get_prs(token, owner, repo, state="all", per_page=30):
        nonlocal call_count
        call_count += 1
        return [
            {
                "number": 1,
                "title": f"PR title v{call_count}",
                "state": "open" if call_count == 1 else "closed",
                "user": {"login": "dev"},
                "updated_at": "2026-01-01T00:00:00Z",
                "merged_at": None,
                "additions": 10,
                "deletions": 0,
                "changed_files": 1,
                "review_comments": 0,
            },
        ]

    async def fake_get_issues(token, owner, repo, state="all", per_page=30):
        return []

    from app.tools import github as github_mod

    monkeypatch.setattr(github_mod, "list_repos", fake_list_repos)
    monkeypatch.setattr(github_mod, "get_pull_requests", fake_get_prs)
    monkeypatch.setattr(github_mod, "get_issues", fake_get_issues)

    # First ingestion
    await ingest_github_signals(db, org_id=1)
    signals_v1 = await _get_signals(db, 1, "github")
    assert len(signals_v1) == 1
    hash_v1 = signals_v1[0].hash
    payload_v1 = json.loads(signals_v1[0].payload_json)
    assert payload_v1["state"] == "open"

    # Second ingestion — same PR, different state
    await ingest_github_signals(db, org_id=1)
    signals_v2 = await _get_signals(db, 1, "github")
    assert len(signals_v2) == 1  # still 1 row
    hash_v2 = signals_v2[0].hash
    payload_v2 = json.loads(signals_v2[0].payload_json)
    assert payload_v2["state"] == "closed"
    assert hash_v2 != hash_v1  # hash changed because payload changed
