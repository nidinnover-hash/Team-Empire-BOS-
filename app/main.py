from contextlib import asynccontextmanager
import asyncio
import secrets
from typing import AsyncGenerator

from fastapi import Depends, FastAPI, Form, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.router import api_router
from app.api.v1.endpoints.ops import run_daily_run_workflow
from app.core.config import format_startup_issues, settings, validate_startup_settings
from app.core.contracts import error_envelope
from app.core.deps import get_current_web_user, get_db, verify_csrf
from app.core.middleware import (
    CorrelationIDMiddleware,
    RateLimitMiddleware,
    RequestLogMiddleware,
    SecurityHeadersMiddleware,
    clear_login_failures,
    check_login_allowed,
    record_login_failure,
)
from app.core.security import create_access_token, decode_access_token, get_current_user, verify_password
from app.db.base import Base
from app.db.session import engine
from app.services import command as command_service
from app.services import contact as contact_service
from app.services import finance as finance_service
from app.services import briefing as briefing_service
from app.services import goal as goal_service
from app.services import intelligence as intelligence_service
from app.services import layers as layers_service
from app.services import memory as memory_service
from app.services import note as note_service
from app.services import organization as organization_service
from app.services import project as project_service
from app.services import task as task_service
from app.services import user as user_service

# Register every model with Base.metadata so create_all sees them
from app.models import approval as _model_approval  # noqa: F401
from app.models import command as _model_command  # noqa: F401
from app.models import conversation as _model_conversation  # noqa: F401
from app.models import contact as _model_contact  # noqa: F401
from app.models import daily_run as _model_daily_run  # noqa: F401
from app.models import decision_trace as _model_decision_trace  # noqa: F401
from app.models import email as _model_email  # noqa: F401
from app.models import event as _model_event  # noqa: F401
from app.models import execution as _model_execution  # noqa: F401
from app.models import finance as _model_finance  # noqa: F401
from app.models import goal as _model_goal  # noqa: F401
from app.models import integration as _model_integration  # noqa: F401
from app.models import memory as _model_memory  # noqa: F401
from app.models import note as _model_note  # noqa: F401
from app.models import organization as _model_organization  # noqa: F401
from app.models import project as _model_project  # noqa: F401
from app.models import task as _model_task  # noqa: F401
from app.models import user as _model_user  # noqa: F401
from app.models import whatsapp_message as _model_whatsapp_message  # noqa: F401
from app.models import chat_message as _model_chat_message  # noqa: F401
from app.models import ai_call_log as _model_ai_call_log  # noqa: F401

# Startup safety guard
_UNSAFE_SECRET_KEYS = {"change_me_in_env", "changeme", "secret", "change-me", ""}
if settings.SECRET_KEY in _UNSAFE_SECRET_KEYS or len(settings.SECRET_KEY) < 32:
    raise RuntimeError(
        "SECRET_KEY is insecure. Set a 32+ character random value in .env. "
        "Generate one: python -c \"import secrets; print(secrets.token_hex(32))\""
    )
_UNSAFE_PASSWORDS = {"demo", "password", "admin", "changeme", "change_me", ""}
if settings.ADMIN_PASSWORD in _UNSAFE_PASSWORDS or len(settings.ADMIN_PASSWORD) < 8:
    raise RuntimeError(
        "ADMIN_PASSWORD is insecure. Set a strong password (8+ chars) in .env."
    )
if settings.ENFORCE_STARTUP_VALIDATION or not settings.DEBUG:
    startup_issues = validate_startup_settings(settings)
    if startup_issues:
        raise RuntimeError(
            "Startup configuration validation failed:\n" + format_startup_issues(startup_issues)
        )

templates = Jinja2Templates(directory="app/templates")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # DB health probe — fail fast if database is unreachable
    from sqlalchemy import text
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    # Production should use migrations only; optional auto-create/seed for local dev.
    if settings.AUTO_CREATE_SCHEMA:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    if settings.AUTO_SEED_DEFAULTS:
        async with AsyncSession(engine) as db:
            org = await organization_service.ensure_default_organization(db)
            await user_service.ensure_default_user(db, organization_id=org.id)
    # Start background sync scheduler
    from app.services.sync_scheduler import start_scheduler, stop_scheduler
    if settings.SYNC_ENABLED:
        start_scheduler(interval_minutes=settings.SYNC_INTERVAL_MINUTES)
    yield
    if settings.SYNC_ENABLED:
        stop_scheduler()
    await engine.dispose()

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# CORS: strict-origin whitelist from config
_cors_origins = [
    o.strip() for o in settings.CORS_ALLOWED_ORIGINS.split(",")
    if o.strip()
]
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-CSRF-Token", "X-Correlation-ID"],
    )

# Middleware is applied in reverse order (last added = outermost)
# SecurityHeaders → CorrelationID → RateLimit → handler
app.add_middleware(RateLimitMiddleware)
app.add_middleware(CorrelationIDMiddleware)
app.add_middleware(RequestLogMiddleware)
app.add_middleware(SecurityHeadersMiddleware)


def _request_id_from_state(request: Request) -> str | None:
    return getattr(request.state, "correlation_id", None)


def _status_code_to_error_code(status_code: int) -> str:
    mapping = {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        409: "conflict",
        422: "validation_error",
        429: "rate_limited",
    }
    return mapping.get(status_code, "http_error")


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=error_envelope(
            code=_status_code_to_error_code(exc.status_code),
            detail=exc.detail,
            request_id=_request_id_from_state(request),
        ),
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=error_envelope(
            code="validation_error",
            detail=exc.errors(),
            request_id=_request_id_from_state(request),
        ),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, _exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content=error_envelope(
            code="internal_error",
            detail="Internal server error",
            request_id=_request_id_from_state(request),
        ),
    )


@app.post("/token")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    from app.logs.audit import record_action
    import logging
    _log = logging.getLogger(__name__)
    client_ip = request.client.host if request.client else "unknown"
    if not check_login_allowed(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Try again later.",
        )
    user = await user_service.get_user_by_email(db, username)
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        record_login_failure(client_ip)
        _log.warning("Failed API login for '%s' from %s", username, client_ip)
        await record_action(
            db,
            event_type="login_failed",
            actor_user_id=None,
            organization_id=user.organization_id if user else 1,
            entity_type="user",
            entity_id=user.id if user else None,
            payload_json={"username": username[:200], "ip": client_ip, "endpoint": "/token"},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username/password",
        )

    access_token = create_access_token(
        {
            "id": user.id,
            "email": user.email,
            "role": user.role,
            "org_id": user.organization_id,
        },
        expires_minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES,
    )
    clear_login_failures(client_ip)
    return {"access_token": access_token, "token_type": "bearer"}


@app.get("/web/login", response_class=HTMLResponse, include_in_schema=False)
async def web_login_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "login.html", {"request": request, "error": None})


@app.post("/web/login")
async def web_login(
    request: Request,
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from app.logs.audit import record_action
    import logging
    _log = logging.getLogger(__name__)
    client_ip = request.client.host if request.client else "unknown"
    if not check_login_allowed(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Try again later.",
        )
    user = await user_service.get_user_by_email(db, username)
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        record_login_failure(client_ip)
        _log.warning("Failed web login for '%s' from %s", username, client_ip)
        await record_action(
            db,
            event_type="login_failed",
            actor_user_id=None,
            organization_id=user.organization_id if user else 1,
            entity_type="user",
            entity_id=user.id if user else None,
            payload_json={"username": username[:200], "ip": client_ip, "endpoint": "/web/login"},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username/password",
        )
    access_token = create_access_token(
        {
            "id": user.id,
            "email": user.email,
            "role": user.role,
            "org_id": user.organization_id,
        },
        expires_minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES,
    )
    clear_login_failures(client_ip)
    csrf_token = secrets.token_urlsafe(32)
    max_age = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    response.set_cookie(
        key="pc_session",
        value=access_token,
        max_age=max_age,
        httponly=True,
        samesite="lax",
        secure=settings.COOKIE_SECURE,
        path="/",
    )
    response.set_cookie(
        key="pc_csrf",
        value=csrf_token,
        max_age=max_age,
        httponly=False,
        samesite="lax",
        secure=settings.COOKIE_SECURE,
        path="/",
    )
    # Kick off a background integration sync (throttled, fire-and-forget)
    if settings.SYNC_ENABLED:
        from app.services.sync_scheduler import trigger_sync_for_org
        asyncio.create_task(trigger_sync_for_org(user.organization_id))
    return {"status": "ok", "email": user.email, "role": user.role}


@app.post("/web/logout")
async def web_logout(
    response: Response,
    _csrf_ok: None = Depends(verify_csrf),
) -> dict:
    response.delete_cookie("pc_session", path="/")
    response.delete_cookie("pc_csrf", path="/")
    return {"status": "logged_out"}


@app.get("/web/api-token", include_in_schema=False)
async def web_api_token(user: dict = Depends(get_current_web_user)) -> dict:
    """Return a fresh Bearer token for the current web session. Used by dashboard JS."""
    token = create_access_token(
        {"id": user["id"], "email": user["email"], "role": user["role"], "org_id": user["org_id"]},
        expires_minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES,
    )
    return {"token": token}


@app.get("/web/session")
async def web_session(request: Request) -> dict:
    token = request.cookies.get("pc_session")
    if not token:
        return {"logged_in": False}
    try:
        payload = decode_access_token(token)
    except ValueError:
        return {"logged_in": False}
    return {
        "logged_in": True,
        "user": {
            "id": payload.get("id"),
            "email": payload.get("email"),
            "role": payload.get("role", "STAFF"),
            "org_id": payload.get("org_id"),
        },
    }


@app.post("/web/agents/chat")
async def web_agent_chat(
    message: str = Form(...),
    force_role: str | None = Form(None),
    _csrf_ok: None = Depends(verify_csrf),
    user: dict = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    from app.agents.orchestrator import AgentChatRequest, run_agent
    from app.services.memory import build_memory_context
    from app.services import chat_history as chat_history_service
    from app.services import conversation_learning as conversation_learning_service

    # Only CEO/ADMIN may force a specific role; other roles get keyword routing
    if force_role and user["role"] not in {"CEO", "ADMIN"}:
        force_role = None

    org_id = int(user["org_id"])
    memory_context = await build_memory_context(db, organization_id=org_id)

    # Load the last 10 turns for multi-turn context
    recent = await chat_history_service.get_recent(db, org_id=org_id, limit=10)
    history = chat_history_service.as_openai_history(recent) or None

    result = await run_agent(
        request=AgentChatRequest(
            message=message,
            force_role=force_role if force_role else None,
        ),
        memory_context=memory_context,
        conversation_history=history,
    )

    # Persist this exchange for future context
    await chat_history_service.save_message(
        db,
        org_id=org_id,
        user_id=int(user["id"]),
        role=result.role,
        user_message=message,
        ai_response=result.response,
    )
    await conversation_learning_service.learn_from_message(
        db=db,
        org_id=org_id,
        actor_user_id=int(user["id"]),
        message=message,
    )

    return JSONResponse(content={
        "role": result.role,
        "response": result.response,
        "requires_approval": result.requires_approval,
        "proposed_actions": [a.model_dump() for a in result.proposed_actions],
    })


@app.get("/web/chat/history", include_in_schema=False)
async def web_chat_history(
    user: dict = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Return the last 20 chat turns for the session user's org."""
    from app.services import chat_history as chat_history_service

    org_id = int(user["org_id"])
    recent = await chat_history_service.get_recent(db, org_id=org_id, limit=20)
    return JSONResponse(content=[
        {
            "id": m.id,
            "role": m.role,
            "user_message": m.user_message,
            "ai_response": m.ai_response,
            "created_at": m.created_at.isoformat(),
        }
        for m in recent
    ])


@app.post("/web/ops/daily-run")
async def web_daily_run(
    draft_email_limit: int = 3,
    team: str | None = None,
    _csrf_ok: None = Depends(verify_csrf),
    user: dict = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    if user["role"] not in {"CEO", "ADMIN", "MANAGER"}:
        raise HTTPException(status_code=403, detail="Insufficient role")
    data = await run_daily_run_workflow(
        db=db,
        org_id=int(user["org_id"]),
        actor_user_id=int(user["id"]),
        draft_email_limit=draft_email_limit,
        team=team,
    )
    return JSONResponse(content=data)


@app.get("/me")
def me(user=Depends(get_current_user)):
    return {
        "email": user["email"],
        "id": user["id"],
        "role": user["role"],
        "org_id": user["org_id"],
    }


@app.get("/health")
def health_check():
    return {"status": "ok"}


if settings.app_mode_normalized == "NIDIN_AI":
    app.include_router(api_router, prefix="/api/v1")
elif settings.app_mode_normalized == "EMPIREO_AI":
    # Scaffold: keep shared router for now. When Empireo-specific endpoints
    # are ready, replace with an Empireo router module here.
    app.include_router(api_router, prefix="/api/v1")
else:
    raise RuntimeError(f"Unsupported APP_MODE: {settings.APP_MODE!r}")


@app.get("/web/integrations", response_class=HTMLResponse, include_in_schema=False)
async def web_integrations(request: Request) -> HTMLResponse:
    token = request.cookies.get("pc_session")
    user = None
    if token:
        try:
            user = decode_access_token(token)
        except ValueError:
            user = None
    if user is None:
        return RedirectResponse(url="/web/login", status_code=302)
    return templates.TemplateResponse(
        request,
        "integrations.html",
        {
            "request": request,
            "session_user": user,
        },
    )


@app.get("/web/talk", response_class=HTMLResponse, include_in_schema=False)
async def web_talk(request: Request) -> HTMLResponse:
    token = request.cookies.get("pc_session")
    user = None
    if token:
        try:
            user = decode_access_token(token)
        except ValueError:
            user = None
    if user is None:
        return RedirectResponse(url="/web/login", status_code=302)
    return templates.TemplateResponse(
        request,
        "talk.html",
        {
            "request": request,
            "session_user": user,
        },
    )


@app.get("/web/data-hub", response_class=HTMLResponse, include_in_schema=False)
async def web_data_hub(request: Request) -> HTMLResponse:
    token = request.cookies.get("pc_session")
    user = None
    if token:
        try:
            user = decode_access_token(token)
        except ValueError:
            user = None
    if user is None:
        return RedirectResponse(url="/web/login", status_code=302)
    return templates.TemplateResponse(
        request,
        "data_hub.html",
        {
            "request": request,
            "session_user": user,
        },
    )


@app.get("/web/observe", response_class=HTMLResponse, include_in_schema=False)
async def web_observe(request: Request) -> HTMLResponse:
    token = request.cookies.get("pc_session")
    user = None
    if token:
        try:
            user = decode_access_token(token)
        except ValueError:
            user = None
    if user is None:
        return RedirectResponse(url="/web/login", status_code=302)
    return templates.TemplateResponse(
        request, "observe.html", {"request": request, "session_user": user},
    )


@app.get("/web/ops-intel", response_class=HTMLResponse, include_in_schema=False)
async def web_ops_intel(request: Request) -> HTMLResponse:
    token = request.cookies.get("pc_session")
    user = None
    if token:
        try:
            user = decode_access_token(token)
        except ValueError:
            user = None
    if user is None:
        return RedirectResponse(url="/web/login", status_code=302)
    return templates.TemplateResponse(
        request, "ops_intel.html", {"request": request, "session_user": user},
    )


@app.get("/web/tasks", response_class=HTMLResponse, include_in_schema=False)
async def web_tasks(request: Request) -> HTMLResponse:
    token = request.cookies.get("pc_session")
    user = None
    if token:
        try:
            user = decode_access_token(token)
        except ValueError:
            user = None
    if user is None:
        return RedirectResponse(url="/web/login", status_code=302)
    return templates.TemplateResponse(
        request, "tasks.html", {"request": request, "session_user": user},
    )


@app.get("/web/talk/bootstrap", include_in_schema=False)
async def web_talk_bootstrap(
    user: dict = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    org_id = int(user["org_id"])
    tasks = await task_service.list_tasks(
        db,
        limit=5,
        is_done=False,
        organization_id=org_id,
    )
    projects = await project_service.list_projects(db, limit=5, organization_id=org_id)
    notes = await note_service.list_notes(db, limit=3, organization_id=org_id)
    profile_memory = await memory_service.get_profile_memory(db, organization_id=org_id)
    executive = await briefing_service.get_executive_briefing(db, org_id=org_id)
    summary = executive.get("team_summary", {})
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
            "id": item.id,
            "key": item.key,
            "value": item.value,
            "category": item.category,
            "updated_at": item.updated_at.isoformat() if item.updated_at else None,
        }
        for item in profile_memory
        if (item.category or "").strip().lower() == "learned"
    ][:12]
    return {
        "welcome": welcome,
        "snapshot": {
            "open_tasks": open_tasks,
            "pending_approvals": pending_approvals,
            "unread_emails": unread_emails,
            "tasks": [{"id": t.id, "title": t.title, "priority": t.priority} for t in tasks],
            "projects": [{"id": p.id, "title": p.title, "status": p.status} for p in projects],
            "notes": [{"id": n.id, "content": n.content} for n in notes],
        },
        "learned_memory": learned_memory,
        "suggested_prompts": [
            "Prioritize my top 3 tasks for today.",
            "Draft responses for my urgent emails.",
            "What approvals need my decision first?",
            "Build a 2-hour execution plan for my current priorities.",
        ],
    }


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    token = request.cookies.get("pc_session")
    user = None
    if token:
        try:
            user = decode_access_token(token)
        except ValueError:
            user = None
    if user is None:
        return RedirectResponse(url="/web/login", status_code=302)
    org_id = int(user["org_id"])

    # Kick off a background integration sync (throttled, fire-and-forget)
    if settings.SYNC_ENABLED:
        from app.services.sync_scheduler import trigger_sync_for_org
        asyncio.create_task(trigger_sync_for_org(org_id))

    # Parallel fetch — all queries are independent reads on the same org
    (
        commands, tasks, notes, projects, goals, contacts,
        finance, finance_efficiency,
        marketing_layer, study_layer, training_layer,
        executive, intelligence_summary, intelligence_diff,
    ) = await asyncio.gather(
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
    )

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
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
            "session_user": user,
        },
    )
