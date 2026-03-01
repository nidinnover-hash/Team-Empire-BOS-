"""Web page routes: dashboard, talk bootstrap, static authenticated pages."""

import asyncio
import logging
import time as _time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_current_web_user, get_db
from app.services import briefing as briefing_service
from app.services import command as command_service
from app.services import contact as contact_service
from app.services import finance as finance_service
from app.services import goal as goal_service
from app.services import intelligence as intelligence_service
from app.services import layers as layers_service
from app.services import memory as memory_service
from app.services import note as note_service
from app.services import project as project_service
from app.services import task as task_service

logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory="app/templates")

# ── Dashboard Cache ──────────────────────────────────────────────────────
_dashboard_cache: dict[int, tuple[float, dict]] = {}
_DASHBOARD_CACHE_MAX_ORGS = 200


def _get_cached_dashboard(org_id: int) -> dict | None:
    if settings.DASHBOARD_CACHE_TTL_SECONDS <= 0:
        return None
    cached = _dashboard_cache.get(org_id)
    if cached is None:
        return None
    ts, data = cached
    if _time.time() - ts >= settings.DASHBOARD_CACHE_TTL_SECONDS:
        _dashboard_cache.pop(org_id, None)
        return None
    return data


def _set_dashboard_cache(org_id: int, data: dict) -> None:
    if settings.DASHBOARD_CACHE_TTL_SECONDS <= 0:
        return
    now = _time.time()
    stale = [k for k, (ts, _) in _dashboard_cache.items() if now - ts >= settings.DASHBOARD_CACHE_TTL_SECONDS]
    for k in stale:
        _dashboard_cache.pop(k, None)
    while len(_dashboard_cache) >= _DASHBOARD_CACHE_MAX_ORGS:
        oldest = min(_dashboard_cache.items(), key=lambda item: item[1][0])[0]
        _dashboard_cache.pop(oldest, None)
    _dashboard_cache[org_id] = (now, data)


def invalidate_dashboard_cache(org_id: int) -> None:
    """Clear cached dashboard data for an org."""
    _dashboard_cache.pop(org_id, None)


async def _get_web_user_or_none(request: Request, db: AsyncSession) -> dict | None:
    """Extract user from session cookie. Returns None if not logged in."""
    token = request.cookies.get("pc_session")
    if not token:
        return None
    try:
        return await get_current_web_user(request=request, session_token=token, db=db)
    except HTTPException:
        return None


def _web_page(template_name: str):
    """Factory for simple authenticated web page endpoints."""
    async def handler(request: Request, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
        user = await _get_web_user_or_none(request, db)
        if user is None:
            return RedirectResponse(url="/web/login", status_code=302)
        nonce = getattr(request.state, "csp_nonce", "")
        return templates.TemplateResponse(
            request, template_name, {"request": request, "session_user": user, "csp_nonce": nonce},
        )
    return handler


router = APIRouter(tags=["Web Pages"])

# Static authenticated pages
router.get("/web/integrations", response_class=HTMLResponse, include_in_schema=False)(_web_page("integrations.html"))
router.get("/web/talk", response_class=HTMLResponse, include_in_schema=False)(_web_page("talk.html"))
router.get("/web/data-hub", response_class=HTMLResponse, include_in_schema=False)(_web_page("data_hub.html"))
router.get("/web/observe", response_class=HTMLResponse, include_in_schema=False)(_web_page("observe.html"))
router.get("/web/ops-intel", response_class=HTMLResponse, include_in_schema=False)(_web_page("ops_intel.html"))
router.get("/web/tasks", response_class=HTMLResponse, include_in_schema=False)(_web_page("tasks.html"))
router.get("/web/webhooks", response_class=HTMLResponse, include_in_schema=False)(_web_page("webhooks.html"))
router.get("/web/notifications", response_class=HTMLResponse, include_in_schema=False)(_web_page("notifications.html"))
router.get("/web/security", response_class=HTMLResponse, include_in_schema=False)(_web_page("security.html"))
router.get("/web/api-keys", response_class=HTMLResponse, include_in_schema=False)(_web_page("api_keys.html"))


@router.get("/web/login", response_class=HTMLResponse, include_in_schema=False)
async def web_login_page(request: Request) -> HTMLResponse:
    nonce = getattr(request.state, "csp_nonce", "")
    return templates.TemplateResponse(request, "login.html", {"request": request, "error": None, "csp_nonce": nonce})


@router.get("/web/talk/bootstrap", include_in_schema=False)
async def web_talk_bootstrap(
    user: dict = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    org_id = int(user["org_id"])
    coros = [
        task_service.list_tasks(db, limit=5, is_done=False, organization_id=org_id),
        project_service.list_projects(db, limit=5, organization_id=org_id),
        note_service.list_notes(db, limit=3, organization_id=org_id),
        memory_service.get_profile_memory(db, organization_id=org_id),
        briefing_service.get_executive_briefing(db, org_id=org_id),
    ]
    results = await asyncio.gather(*coros, return_exceptions=True)
    tasks = results[0] if not isinstance(results[0], BaseException) else []
    projects = results[1] if not isinstance(results[1], BaseException) else []
    notes = results[2] if not isinstance(results[2], BaseException) else []
    profile_memory = results[3] if not isinstance(results[3], BaseException) else []
    executive = results[4] if not isinstance(results[4], BaseException) else {}

    summary = executive.get("team_summary", {}) if isinstance(executive, dict) else {}
    open_tasks = len(tasks)
    pending_approvals = int(summary.get("pending_approvals", 0) or 0)
    unread_emails = int(summary.get("unread_emails", 0) or 0)

    welcome = (
        f"Good to see you, {user['email']}. "
        f"Right now: {open_tasks} open tasks, {pending_approvals} pending approvals, "
        f"and {unread_emails} unread emails. Tell me what you want to execute first."
    )
    learned_memory = [
        {
            "id": getattr(item, "id", None),
            "key": getattr(item, "key", ""),
            "value": getattr(item, "value", ""),
            "category": getattr(item, "category", None),
            "updated_at": (
                item.updated_at.isoformat()
                if getattr(item, "updated_at", None)
                else None
            ),
        }
        for item in profile_memory
        if str(getattr(item, "category", "") or "").strip().lower() == "learned"
    ][:12]
    return {
        "welcome": welcome,
        "snapshot": {
            "open_tasks": open_tasks,
            "pending_approvals": pending_approvals,
            "unread_emails": unread_emails,
            "tasks": [
                {
                    "id": getattr(t, "id", None),
                    "title": getattr(t, "title", ""),
                    "priority": getattr(t, "priority", None),
                }
                for t in tasks
            ],
            "projects": [
                {
                    "id": getattr(p, "id", None),
                    "title": getattr(p, "title", ""),
                    "status": getattr(p, "status", None),
                }
                for p in projects
            ],
            "notes": [
                {"id": getattr(n, "id", None), "content": getattr(n, "content", "")}
                for n in notes
            ],
        },
        "learned_memory": learned_memory,
        "suggested_prompts": [
            "Prioritize my top 3 tasks for today.",
            "Draft responses for my urgent emails.",
            "What approvals need my decision first?",
            "Build a 2-hour execution plan for my current priorities.",
        ],
    }


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    user = await _get_web_user_or_none(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=302)
    org_id = int(user["org_id"])

    if settings.SYNC_ENABLED:
        from app.services.sync_scheduler import trigger_sync_for_org
        await trigger_sync_for_org(org_id)

    from app.services.sync_scheduler import get_last_synced_for_org
    last_synced_at = get_last_synced_for_org(org_id)

    # Check dashboard cache
    cached = _get_cached_dashboard(org_id)
    if cached is not None:
        cached["request"] = request
        cached["session_user"] = user
        cached["csp_nonce"] = getattr(request.state, "csp_nonce", "")
        cached["last_synced_at"] = last_synced_at
        return templates.TemplateResponse(request, "dashboard.html", cached)

    _DASHBOARD_DEFAULTS: list[Any] = [
        [], [], [], [], [], [],
        {"total_income": 0, "total_expense": 0, "balance": 0},
        None, {}, {}, {},
        {}, None, None,
        {"critical": 0, "high": 0, "recent": []},
    ]
    from app.services import compliance_engine
    try:
        _raw_results = await asyncio.wait_for(
            asyncio.gather(
                command_service.list_commands(db, limit=10, organization_id=org_id),
                task_service.list_tasks(db, limit=20, is_done=False, organization_id=org_id),
                note_service.list_notes(db, limit=10, organization_id=org_id),
                project_service.list_projects(db, limit=10, organization_id=org_id),
                goal_service.list_goals(db, limit=10, organization_id=org_id),
                contact_service.list_contacts(db, limit=8, organization_id=org_id),
                finance_service.get_summary(db, organization_id=org_id),
                finance_service.get_expenditure_efficiency(db, organization_id=org_id, window_days=30),
                layers_service.get_marketing_layer(db, organization_id=org_id, window_days=30),
                layers_service.get_study_layer(db, organization_id=org_id, window_days=30),
                layers_service.get_training_layer(db, organization_id=org_id, window_days=30),
                briefing_service.get_executive_briefing(db, org_id=org_id),
                intelligence_service.build_executive_summary(db=db, organization_id=org_id, window_days=7),
                intelligence_service.build_change_since_yesterday(db=db, organization_id=org_id),
                compliance_engine.latest_report(db, org_id),
                return_exceptions=True,
            ),
            timeout=15.0,
        )
    except TimeoutError:
        logger.warning("Dashboard gather timed out for org=%d", org_id)
        _raw_results = _DASHBOARD_DEFAULTS[:15]

    _defaults = _DASHBOARD_DEFAULTS[:15]
    _results = []
    for i, val in enumerate(_raw_results):
        if isinstance(val, BaseException):
            logger.warning("Dashboard query %d failed for org=%d: %s", i, org_id, val)
            _results.append(_defaults[i] if i < len(_defaults) else None)
        else:
            _results.append(val)
    (
        commands, tasks, notes, projects, goals, contacts,
        finance, finance_efficiency,
        marketing_layer, study_layer, training_layer,
        executive, intelligence_summary, intelligence_diff,
        compliance_report,
    ) = _results

    ceo_action = _extract_ceo_action(compliance_report)

    ctx = {
        "request": request,
        "commands": commands,
        "tasks": tasks,
        "notes": notes,
        "projects": projects,
        "goals": goals,
        "contacts": contacts,
        "finance": finance,
        "finance_efficiency": finance_efficiency,
        "marketing_layer": marketing_layer,
        "study_layer": study_layer,
        "training_layer": training_layer,
        "executive": executive,
        "intelligence_summary": intelligence_summary,
        "intelligence_diff": intelligence_diff,
        "ceo_action": ceo_action,
        "session_user": user,
        "last_synced_at": last_synced_at,
        "csp_nonce": getattr(request.state, "csp_nonce", ""),
    }
    # Cache data (exclude request-specific fields)
    _set_dashboard_cache(org_id, {
        k: v for k, v in ctx.items()
        if k not in ("request", "session_user", "csp_nonce", "last_synced_at")
    })

    return templates.TemplateResponse(request, "dashboard.html", ctx)


def _extract_ceo_action(compliance_report) -> dict:
    """Parse compliance report into CEO action summary."""
    ceo_action: dict[str, Any] = {"critical": 0, "high": 0, "recent": []}
    if isinstance(compliance_report, dict):
        violations = compliance_report.get("violations")
        if isinstance(violations, list):
            ceo_action["critical"] = sum(
                1 for v in violations
                if isinstance(v, dict) and str(v.get("severity", "")).upper() == "CRITICAL"
            )
            ceo_action["high"] = sum(
                1 for v in violations
                if isinstance(v, dict) and str(v.get("severity", "")).upper() == "HIGH"
            )
            ceo_action["recent"] = [
                {
                    "title": str(v.get("title") or "Policy issue"),
                    "severity": str(v.get("severity") or "MED").upper(),
                    "platform": str(v.get("platform") or "unknown"),
                }
                for v in violations[:5]
                if isinstance(v, dict)
            ]
    return ceo_action
