"""Tests for the 34-item improvement sweep."""


from app.core.security import create_access_token


def _ceo_headers(org_id: int = 1) -> dict:
    token = create_access_token({"id": 1, "email": "ceo@org1.com", "role": "CEO", "org_id": org_id, "token_version": 1})
    return {"Authorization": f"Bearer {token}"}


def _staff_headers(org_id: int = 1) -> dict:
    token = create_access_token({"id": 4, "email": "staff@org1.com", "role": "STAFF", "org_id": org_id, "token_version": 1})
    return {"Authorization": f"Bearer {token}"}


# ── SEC-1: CSRF constant-time comparison ──────────────────────────────────────

def test_csrf_uses_hmac_compare_digest():
    """verify_csrf uses hmac.compare_digest, not ==."""
    import inspect

    from app.core import deps
    source = inspect.getsource(deps.verify_csrf)
    assert "hmac.compare_digest" in source
    assert "csrf_cookie != csrf_header" not in source


# ── ARCH-7: ALGORITHM constrained to HS256 ──────────────────────────────────

def test_algorithm_is_literal_hs256():
    """Settings.ALGORITHM should be Literal['HS256']."""
    from app.core.config import Settings
    field = Settings.model_fields["ALGORITHM"]
    assert "HS256" in str(field.annotation)


# ── FEAT-1: Task update now supports all fields ──────────────────────────────

async def test_task_update_title(client):
    """PATCH /tasks/{id} can update title."""
    resp = await client.post(
        "/api/v1/tasks",
        json={"title": "Original Title", "priority": 2},
        headers=_ceo_headers(),
    )
    assert resp.status_code == 201
    task_id = resp.json()["id"]

    resp = await client.patch(
        f"/api/v1/tasks/{task_id}",
        json={"title": "Updated Title"},
        headers=_ceo_headers(),
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "Updated Title"


async def test_task_update_priority(client):
    """PATCH /tasks/{id} can update priority."""
    resp = await client.post(
        "/api/v1/tasks",
        json={"title": "Priority test", "priority": 1},
        headers=_ceo_headers(),
    )
    task_id = resp.json()["id"]

    resp = await client.patch(
        f"/api/v1/tasks/{task_id}",
        json={"priority": 4},
        headers=_ceo_headers(),
    )
    assert resp.status_code == 200
    assert resp.json()["priority"] == 4


# ── FEAT-5: Task delete endpoint ──────────────────────────────────────────────

async def test_task_delete(client):
    """DELETE /tasks/{id} removes a task."""
    resp = await client.post(
        "/api/v1/tasks",
        json={"title": "To delete"},
        headers=_ceo_headers(),
    )
    task_id = resp.json()["id"]

    resp = await client.delete(
        f"/api/v1/tasks/{task_id}",
        headers=_ceo_headers(),
    )
    assert resp.status_code == 204

    # Verify it's gone
    resp = await client.get("/api/v1/tasks", headers=_ceo_headers())
    assert not any(t["id"] == task_id for t in resp.json())


async def test_task_delete_staff_forbidden(client):
    """STAFF cannot delete tasks."""
    resp = await client.post(
        "/api/v1/tasks",
        json={"title": "Protected"},
        headers=_ceo_headers(),
    )
    task_id = resp.json()["id"]

    resp = await client.delete(
        f"/api/v1/tasks/{task_id}",
        headers=_staff_headers(),
    )
    assert resp.status_code == 403


async def test_task_delete_not_found(client):
    """DELETE on non-existent task returns 404."""
    resp = await client.delete("/api/v1/tasks/99999", headers=_ceo_headers())
    assert resp.status_code == 404


# ── RELY-4: Approval timeline uses DB-level pagination ────────────────────────

async def test_approval_timeline_pagination(client):
    """Timeline endpoint accepts limit and offset params."""
    resp = await client.get(
        "/api/v1/approvals/timeline?limit=5&offset=0",
        headers=_ceo_headers(),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "pending_count" in data


# ── ARCH-2: ProposedAction extraction is now enabled ─────────────────────────

def test_run_agent_calls_extract_proposed_actions():
    """run_agent should call extract_proposed_actions for structured intent."""
    import inspect

    from app.agents import orchestrator
    source = inspect.getsource(orchestrator.run_agent)
    assert "extract_proposed_actions" in source


# ── RELY-6: Memory context cache ─────────────────────────────────────────────

def test_memory_context_cache_exists():
    """Memory service should have a cache dict and invalidation function."""
    from app.services.memory import _memory_context_cache, invalidate_memory_cache
    assert isinstance(_memory_context_cache, dict)
    # Invalidation should work without error
    invalidate_memory_cache(999)


# ── ARCH-6: Login authentication is deduplicated ──────────────────────────────

def test_authenticate_user_helper_exists():
    """authenticate_user should be defined as a shared helper."""
    from app.web._helpers import authenticate_user, create_jwt
    assert callable(authenticate_user)
    assert callable(create_jwt)


# ── PROD-6: Morning briefing uses IST date ───────────────────────────────────

def test_morning_briefing_uses_ist_date():
    """_check_morning_briefing should use local_now.date(), not date.today()."""
    import inspect

    from app.services import sync_scheduler
    source = inspect.getsource(sync_scheduler._check_morning_briefing)
    assert "today_ist = local_now.date()" in source
    assert "date.today()" not in source


# ── RELY-2: Scheduler loop isolates sessions per org ─────────────────────────

def test_scheduler_loop_isolates_sessions():
    """Scheduler loop should open a fresh session per org."""
    import inspect

    from app.services import sync_scheduler
    source = inspect.getsource(sync_scheduler._scheduler_loop)
    # Should fetch orgs and run them through isolated pools
    assert "list_organizations" in source
    # Each org gets its own session (via pool runner or direct)
    assert source.count("async with") >= 1
    # Uses org pool pattern for isolation
    assert "_run_org_pool" in source


# ── FEAT-6: Chat retention cleanup exists ─────────────────────────────────────

def test_chat_retention_cleanup_exists():
    """_cleanup_old_chat_messages function should exist and be called in loop."""
    import inspect

    from app.services import sync_scheduler
    assert hasattr(sync_scheduler, "_cleanup_old_chat_messages")
    loop_source = inspect.getsource(sync_scheduler._scheduler_loop)
    assert "_cleanup_old_chat_messages" in loop_source


# ── PROD-4: _log_ai_call accepts optional db param ──────────────────────────

def test_log_ai_call_accepts_db_param():
    """_log_ai_call should accept an optional db parameter."""
    import inspect

    from app.services.ai_router import _log_ai_call
    sig = inspect.signature(_log_ai_call)
    assert "db" in sig.parameters


# ── SEC-3: Login is under rate limiter ────────────────────────────────────────

def test_login_not_exempt_from_rate_limit():
    """/web/login should not be in rate limit exempt list."""
    from app.core.middleware import _EXEMPT_PREFIXES
    assert "/web/login" not in _EXEMPT_PREFIXES


# ── ARCH-1: No more org_id=1 defaults ────────────────────────────────────────

def test_no_org_id_default_1_in_endpoints():
    """No endpoint file should contain .get('org_id', 1)."""
    import pathlib
    endpoints_dir = pathlib.Path("app/api/v1/endpoints")
    for f in endpoints_dir.glob("*.py"):
        content = f.read_text()
        assert '.get("org_id", 1)' not in content, f"Found org_id default in {f.name}"
        assert ".get('org_id', 1)" not in content, f"Found org_id default in {f.name}"


# ── PROD-1: Alembic migration for chat_messages ──────────────────────────────

def test_chat_messages_migration_exists():
    """Migration 0022 should create the chat_messages table."""
    import pathlib
    migrations = list(pathlib.Path("alembic/versions").glob("*0022*chat_messages*"))
    assert len(migrations) == 1


# ── Config: CHAT_HISTORY_RETENTION_DAYS exists ────────────────────────────────

def test_chat_retention_config():
    """Settings should have CHAT_HISTORY_RETENTION_DAYS."""
    from app.core.config import settings
    assert hasattr(settings, "CHAT_HISTORY_RETENTION_DAYS")
    assert settings.CHAT_HISTORY_RETENTION_DAYS == 90
