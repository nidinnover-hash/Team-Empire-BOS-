from contextlib import asynccontextmanager
import asyncio
import secrets
from typing import Any, AsyncGenerator, cast

from fastapi import Depends, FastAPI, Form, HTTPException, Request, Response, status
from fastapi.encoders import jsonable_encoder
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
from app.core.deps import get_current_api_user, get_current_web_user, get_db, verify_csrf
from app.core.purpose import resolve_login_profile
from app.core.middleware import (
    CorrelationIDMiddleware,
    RateLimitMiddleware,
    RequestLogMiddleware,
    SecurityHeadersMiddleware,
    clear_login_failures,
    check_login_allowed,
    record_login_failure,
)
from app.core.security import create_access_token, decode_access_token, verify_password
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
from app.services import talk_commands as talk_command_service
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
from app.models import ceo_control as _model_ceo_control  # noqa: F401
from app.models import github as _model_github  # noqa: F401
from app.models import daily_plan as _model_daily_plan  # noqa: F401
from app.models import employee as _model_employee  # noqa: F401
from app.models import integration_signal as _model_integration_signal  # noqa: F401
from app.models import ops_metrics as _model_ops_metrics  # noqa: F401
from app.models import decision_log as _model_decision_log  # noqa: F401
from app.models import policy_rule as _model_policy_rule  # noqa: F401
from app.models import weekly_report as _model_weekly_report  # noqa: F401
from app.models import org_membership as _model_org_membership  # noqa: F401
from app.models import org_role_permission as _model_org_role_permission  # noqa: F401
from app.models import clone_performance as _model_clone_performance  # noqa: F401
from app.models import clone_control as _model_clone_control  # noqa: F401
from app.models import social as _model_social  # noqa: F401

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
if settings.TOKEN_ENCRYPTION_KEY and settings.TOKEN_ENCRYPTION_KEY == settings.SECRET_KEY:
    raise RuntimeError(
        "TOKEN_ENCRYPTION_KEY must differ from SECRET_KEY for proper key separation. "
        "Generate a new one: python -c \"import secrets; print(secrets.token_hex(32))\""
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
    from app.core.logging_config import configure_logging
    configure_logging(log_format=settings.LOG_FORMAT, log_level=settings.LOG_LEVEL)

    import time as _time
    global _server_start_time
    _server_start_time = _time.time()
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
    # Start background sync scheduler.
    # In production with multiple Gunicorn workers, set RUN_SCHEDULER=false and
    # run the scheduler as a separate systemd service (see deploy/scheduler.service).
    from app.services.sync_scheduler import start_scheduler, stop_scheduler
    run_scheduler = settings.RUN_SCHEDULER
    if settings.SYNC_ENABLED and run_scheduler:
        start_scheduler(interval_minutes=settings.SYNC_INTERVAL_MINUTES)
    yield
    if settings.SYNC_ENABLED and run_scheduler:
        await stop_scheduler()
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
            detail=jsonable_encoder(exc.errors()),
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


# Dummy hash for timing-safe login — always run verify_password even when
# user doesn't exist so response time doesn't reveal valid usernames.
_DUMMY_HASH = "pbkdf2_sha256$100000$QUFBQUFBQUFBQUFBQUFB$QUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQQ=="


def _effective_token_expiry_minutes() -> int:
    session_cap_minutes = max(1, int(settings.ACCOUNT_SESSION_MAX_HOURS)) * 60
    return min(int(settings.ACCESS_TOKEN_EXPIRE_MINUTES), session_cap_minutes)


def _enforce_password_login_policy() -> None:
    # Password login is incompatible with strict SSO-only mode.
    if settings.ACCOUNT_SSO_REQUIRED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Password login is disabled: SSO is required by policy.",
        )


async def _authenticate_user(
    db: AsyncSession, username: str, password: str, client_ip: str, endpoint: str,
):
    """Shared authentication logic for /token and /web/login."""
    from app.logs.audit import record_action
    import logging
    _log = logging.getLogger(__name__)

    if not check_login_allowed(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Try again later.",
        )
    user = await user_service.get_user_by_email(db, username)

    # Constant-time: always run PBKDF2 so response time doesn't leak
    # whether the username exists.  Offload to thread to avoid blocking
    # the event loop (~100ms of CPU per call).
    if user is None or not user.is_active:
        await asyncio.to_thread(verify_password, password, _DUMMY_HASH)
        valid = False
    else:
        valid = await asyncio.to_thread(verify_password, password, user.password_hash)

    if not valid:
        record_login_failure(client_ip)
        _log.warning("Failed login for '%s' from %s on %s", username, client_ip, endpoint)
        audit_kwargs: dict = {
            "event_type": "login_failed",
            "actor_user_id": user.id if user else None,
            "entity_type": "user",
            "entity_id": user.id if user else None,
            "payload_json": {"username": username[:200], "ip": client_ip, "endpoint": endpoint},
        }
        if user:
            audit_kwargs["organization_id"] = user.organization_id
        await record_action(db, **audit_kwargs)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username/password",
        )
    clear_login_failures(client_ip)
    return user


def _create_jwt(user) -> str:
    """Create a JWT token for the authenticated user."""
    purpose_profile = _resolve_login_profile(user.email)
    token_version = int(getattr(user, "token_version", 1) or 1)
    return cast(str, create_access_token(
        {
            "id": user.id,
            "email": user.email,
            "role": user.role,
            "org_id": user.organization_id,
            "token_version": token_version,
            "purpose": purpose_profile["purpose"],
            "default_theme": purpose_profile["default_theme"],
            "default_avatar_mode": purpose_profile["default_avatar_mode"],
        },
        expires_minutes=_effective_token_expiry_minutes(),
    ))


def _resolve_login_profile(email: str) -> dict[str, str]:
    return resolve_login_profile(email)


def _read_avatar_scope(user: dict[str, Any], requested_mode: str) -> str:
    if not settings.PURPOSE_STRICT_BARRIERS:
        return requested_mode
    purpose = str(user.get("purpose") or "professional").strip().lower()
    if purpose == "professional":
        return "professional"
    if purpose == "entertainment":
        return "entertainment"
    if purpose == "personal":
        # Asymmetric barrier: personal lane may read CEO/professional lane.
        if requested_mode in {"personal", "professional"}:
            return requested_mode
        return "personal"
    return "professional"


def _write_avatar_scope(user: dict[str, Any], requested_mode: str) -> str:
    if not settings.PURPOSE_STRICT_BARRIERS:
        return requested_mode
    purpose = str(user.get("purpose") or "professional").strip().lower()
    if purpose == "personal":
        # Never write personal account messages into CEO/professional lane.
        return "personal"
    if purpose in {"professional", "entertainment"}:
        return purpose
    return "professional"


@app.post("/token")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    _enforce_password_login_policy()
    client_ip = request.client.host if request.client else "unknown"
    user = await _authenticate_user(db, username, password, client_ip, "/token")
    return {"access_token": _create_jwt(user), "token_type": "bearer"}


@app.get("/web/login", response_class=HTMLResponse, include_in_schema=False)
async def web_login_page(request: Request) -> HTMLResponse:
    nonce = getattr(request.state, "csp_nonce", "")
    return templates.TemplateResponse(request, "login.html", {"request": request, "error": None, "csp_nonce": nonce})


@app.post("/web/login")
async def web_login(
    request: Request,
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    _enforce_password_login_policy()
    client_ip = request.client.host if request.client else "unknown"
    user = await _authenticate_user(db, username, password, client_ip, "/web/login")
    access_token = _create_jwt(user)
    purpose_profile = _resolve_login_profile(user.email)
    csrf_token = secrets.token_urlsafe(32)
    max_age = _effective_token_expiry_minutes() * 60
    # Clear stale cookies before setting new ones (prevents session fixation)
    for _cookie_name in ("pc_session", "pc_csrf", "pc_theme_scope", "pc_theme_default", "pc_avatar_default"):
        response.delete_cookie(_cookie_name, path="/")
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
    response.set_cookie(
        key="pc_theme_scope",
        value=purpose_profile["purpose"],
        max_age=max_age,
        httponly=False,
        samesite="lax",
        secure=settings.COOKIE_SECURE,
        path="/",
    )
    response.set_cookie(
        key="pc_theme_default",
        value=purpose_profile["default_theme"],
        max_age=max_age,
        httponly=False,
        samesite="lax",
        secure=settings.COOKIE_SECURE,
        path="/",
    )
    response.set_cookie(
        key="pc_avatar_default",
        value=purpose_profile["default_avatar_mode"],
        max_age=max_age,
        httponly=False,
        samesite="lax",
        secure=settings.COOKIE_SECURE,
        path="/",
    )
    # Kick off a background integration sync (throttled, fire-and-forget)
    if settings.SYNC_ENABLED:
        from app.services.sync_scheduler import trigger_sync_for_org
        await trigger_sync_for_org(user.organization_id)
    return {"status": "ok", "email": user.email, "role": user.role}


@app.post("/web/logout")
async def web_logout(
    response: Response,
    _csrf_ok: None = Depends(verify_csrf),
) -> dict:
    response.delete_cookie("pc_session", path="/")
    response.delete_cookie("pc_csrf", path="/")
    response.delete_cookie("pc_theme_scope", path="/")
    response.delete_cookie("pc_theme_default", path="/")
    response.delete_cookie("pc_avatar_default", path="/")
    return {"status": "logged_out"}


@app.get("/web/api-token", include_in_schema=False)
async def web_api_token(user: dict = Depends(get_current_web_user)) -> dict:
    """Return a fresh Bearer token for the current web session. Used by dashboard JS."""
    purpose_profile = _resolve_login_profile(str(user.get("email", "")))
    purpose = str(user.get("purpose") or purpose_profile["purpose"])
    default_theme = str(user.get("default_theme") or purpose_profile["default_theme"])
    default_avatar_mode = str(user.get("default_avatar_mode") or purpose_profile["default_avatar_mode"])
    token = create_access_token(
        {
            "id": user["id"],
            "email": user["email"],
            "role": user["role"],
            "org_id": user["org_id"],
            "token_version": int(user.get("token_version") or 1),
            "purpose": purpose,
            "default_theme": default_theme,
            "default_avatar_mode": default_avatar_mode,
        },
        expires_minutes=_effective_token_expiry_minutes(),
    )
    return {"token": token}


@app.get("/web/session")
async def web_session(request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    token = request.cookies.get("pc_session")
    if not token:
        return {"logged_in": False}
    try:
        payload = decode_access_token(token)
    except ValueError:
        return {"logged_in": False}
    try:
        user = await get_current_web_user(session_token=token, db=db)
    except HTTPException:
        return {"logged_in": False}
    return {
        "logged_in": True,
        "user": {
            "id": user.get("id"),
            "email": user.get("email"),
            "role": user.get("role", "STAFF"),
            "org_id": user.get("org_id"),
            "purpose": user.get("purpose", "professional"),
            "default_theme": payload.get("default_theme", settings.PURPOSE_DEFAULT_THEME_PROFESSIONAL),
            "default_avatar_mode": payload.get("default_avatar_mode", "professional"),
        },
    }


@app.post("/web/agents/chat")
async def web_agent_chat(
    message: str = Form(..., max_length=10_000),
    force_role: str | None = Form(None, max_length=50),
    avatar_mode: str | None = Form(None, max_length=30),
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
    default_avatar = str(user.get("default_avatar_mode") or "professional")
    avatar_mode = (avatar_mode or default_avatar).strip().lower()
    if avatar_mode not in {"personal", "professional", "entertainment"}:
        avatar_mode = "professional"
    read_avatar_mode = _read_avatar_scope(user, avatar_mode)
    write_avatar_mode = _write_avatar_scope(user, avatar_mode)

    org_id = int(user["org_id"])
    memory_context = await build_memory_context(
        db,
        organization_id=org_id,
        categories=(
            None
            if read_avatar_mode == "professional"
            else ["identity", "preference", "learned", "personal", "entertainment"]
        ),
    )
    avatar_memories = await memory_service.get_avatar_memory(
        db,
        organization_id=org_id,
        avatar_mode=read_avatar_mode,
    )
    if avatar_memories:
        avatar_block = "\n".join(f"- {item.key}: {item.value}" for item in avatar_memories[:30])
        memory_context = f"{memory_context}\n\n[AVATAR:{read_avatar_mode.upper()}]\n{avatar_block}"

    # Load the last 10 turns for multi-turn context
    recent = await chat_history_service.get_recent(
        db,
        org_id=org_id,
        limit=10,
        avatar_mode=read_avatar_mode,
    )
    history = chat_history_service.as_openai_history(recent) or None

    command_result = await talk_command_service.maybe_handle_talk_command(
        db=db,
        org_id=org_id,
        message=message,
        actor_role=user.get("role"),
    )
    if command_result.handled:
        await chat_history_service.save_message(
            db,
            org_id=org_id,
            user_id=int(user["id"]),
            role=command_result.role,
            user_message=message,
            ai_response=command_result.response,
            avatar_mode=write_avatar_mode,
        )
        await conversation_learning_service.learn_from_message(
            db=db,
            org_id=org_id,
            actor_user_id=int(user["id"]),
            message=message,
        )
        return JSONResponse(content={
            "role": command_result.role,
            "response": command_result.response,
            "requires_approval": command_result.requires_approval,
            "proposed_actions": [],
        })

    result = await run_agent(
        request=AgentChatRequest(
            message=message,
            force_role=force_role if force_role else None,
            avatar_mode=read_avatar_mode if read_avatar_mode else None,
        ),
        memory_context=memory_context,
        conversation_history=history,
        organization_id=org_id,
    )

    # Persist this exchange for future context
    await chat_history_service.save_message(
        db,
        org_id=org_id,
        user_id=int(user["id"]),
        role=result.role,
        user_message=message,
        ai_response=result.response,
        avatar_mode=write_avatar_mode,
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
    avatar_mode: str | None = None,
    user: dict = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Return the last 20 chat turns for the session user's org."""
    from app.services import chat_history as chat_history_service

    org_id = int(user["org_id"])
    avatar_mode = _read_avatar_scope(
        user,
        (avatar_mode or str(user.get("default_avatar_mode") or "professional")).strip().lower(),
    )
    recent = await chat_history_service.get_recent(
        db,
        org_id=org_id,
        limit=20,
        avatar_mode=avatar_mode,
    )
    return JSONResponse(content=[
        {
            "id": m.id,
            "role": chat_history_service.decode_role(m.role),
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
def me(user=Depends(get_current_api_user)):
    return {
        "email": user["email"],
        "id": user["id"],
        "role": user["role"],
        "org_id": user["org_id"],
    }


_server_start_time: float | None = None

@app.get("/health")
async def health_check():
    import logging
    import time
    from sqlalchemy import text
    from fastapi.responses import JSONResponse as _JSONResponse
    # DB check — uses raw engine connection, independent of the DI pool
    db_ok = True
    try:
        async with engine.connect() as conn:
            await asyncio.wait_for(conn.execute(text("SELECT 1")), timeout=3.0)
    except Exception as exc:
        logging.getLogger(__name__).warning("Health DB probe failed: %s", type(exc).__name__)
        db_ok = False

    # Scheduler status
    from app.services.sync_scheduler import _scheduler_task
    scheduler_running = (
        _scheduler_task is not None and not _scheduler_task.done()
    ) if _scheduler_task is not None else False

    uptime = round(time.time() - _server_start_time, 1) if _server_start_time else 0
    payload = {
        "status": "ok" if db_ok else "degraded",
        "version": settings.APP_VERSION,
        "uptime_seconds": uptime,
        "database": "ok" if db_ok else "error",
        "scheduler": "running" if scheduler_running else "stopped",
    }
    return _JSONResponse(content=payload, status_code=200 if db_ok else 503)


if settings.app_mode_normalized == "NIDIN_AI":
    app.include_router(api_router, prefix="/api/v1")
elif settings.app_mode_normalized == "EMPIREO_AI":
    # Scaffold: keep shared router for now. When Empireo-specific endpoints
    # are ready, replace with an Empireo router module here.
    app.include_router(api_router, prefix="/api/v1")
else:
    raise RuntimeError(f"Unsupported APP_MODE: {settings.APP_MODE!r}")


async def _get_web_user_or_none(request: Request, db: AsyncSession) -> dict | None:
    """Extract user from session cookie. Returns None if not logged in."""
    token = request.cookies.get("pc_session")
    if not token:
        return None
    try:
        return await get_current_web_user(session_token=token, db=db)
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

app.get("/web/integrations", response_class=HTMLResponse, include_in_schema=False)(_web_page("integrations.html"))
app.get("/web/talk", response_class=HTMLResponse, include_in_schema=False)(_web_page("talk.html"))
app.get("/web/data-hub", response_class=HTMLResponse, include_in_schema=False)(_web_page("data_hub.html"))
app.get("/web/observe", response_class=HTMLResponse, include_in_schema=False)(_web_page("observe.html"))
app.get("/web/ops-intel", response_class=HTMLResponse, include_in_schema=False)(_web_page("ops_intel.html"))
app.get("/web/tasks", response_class=HTMLResponse, include_in_schema=False)(_web_page("tasks.html"))


@app.get("/web/talk/bootstrap", include_in_schema=False)
async def web_talk_bootstrap(
    user: dict = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    org_id = int(user["org_id"])
    # Fire all queries concurrently; each returns independently so partial results survive timeouts
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
    user = await _get_web_user_or_none(request, db)
    if user is None:
        return RedirectResponse(url="/web/login", status_code=302)
    org_id = int(user["org_id"])

    # Kick off a background integration sync (throttled, fire-and-forget)
    if settings.SYNC_ENABLED:
        from app.services.sync_scheduler import trigger_sync_for_org
        await trigger_sync_for_org(org_id)

    from app.services.sync_scheduler import get_last_synced_for_org
    last_synced_at = get_last_synced_for_org(org_id)

    # Parallel fetch — all queries are independent reads on the same org.
    # Timeout prevents dashboard from hanging if any single query stalls.
    _DASHBOARD_DEFAULTS: tuple[Any, ...] = (
        [], [], [], [], [], [],  # commands, tasks, notes, projects, goals, contacts
        {"total_income": 0, "total_expense": 0, "balance": 0},  # finance
        None, {}, {}, {},  # finance_efficiency, marketing, study, training
        {}, None, None,  # executive, intelligence_summary, intelligence_diff
        {"critical": 0, "high": 0, "recent": []},  # ceo_action
    )
    from app.services import compliance_engine
    try:
        (
            commands, tasks, notes, projects, goals, contacts,
            finance, finance_efficiency,
            marketing_layer, study_layer, training_layer,
            executive, intelligence_summary, intelligence_diff,
            compliance_report,
        ) = await asyncio.wait_for(
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
            ),
            timeout=15.0,
        )
    except asyncio.TimeoutError:
        import logging as _logging
        _logging.getLogger(__name__).warning("Dashboard gather timed out for org=%d", org_id)
        (
            commands, tasks, notes, projects, goals, contacts,
            finance, finance_efficiency,
            marketing_layer, study_layer, training_layer,
            executive, intelligence_summary, intelligence_diff,
            compliance_report,
        ) = _DASHBOARD_DEFAULTS

    ceo_action = {"critical": 0, "high": 0, "recent": []}
    if isinstance(compliance_report, dict):
        violations = compliance_report.get("violations")
        if isinstance(violations, list):
            ceo_action["critical"] = sum(1 for v in violations if isinstance(v, dict) and str(v.get("severity", "")).upper() == "CRITICAL")
            ceo_action["high"] = sum(1 for v in violations if isinstance(v, dict) and str(v.get("severity", "")).upper() == "HIGH")
            ceo_action["recent"] = [
                {
                    "title": str(v.get("title") or "Policy issue"),
                    "severity": str(v.get("severity") or "MED").upper(),
                    "platform": str(v.get("platform") or "unknown"),
                }
                for v in violations[:5]
                if isinstance(v, dict)
            ]

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
            "ceo_action": ceo_action,
            "session_user": user,
            "last_synced_at": last_synced_at,
            "csp_nonce": getattr(request.state, "csp_nonce", ""),
        },
    )
