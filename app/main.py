"""Application entry point — FastAPI app, middleware, lifespan, exception handlers.

Route modules:
  - API endpoints: app.api.v1.router
  - Web auth (login/logout/session): app.web.auth
  - Web pages (dashboard, talk): app.web.pages
  - Web chat (agent, history): app.web.chat
"""
# ruff: noqa: E402

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, ORJSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.router import api_router
from app.core.config import format_startup_issues, settings, validate_startup_settings
from app.core.contracts import error_envelope
from app.core.deps import get_current_api_user, get_db
from app.core.middleware import (
    CorrelationIDMiddleware,
    RateLimitMiddleware,
    RequestBodyLimitMiddleware,
    RequestLogMiddleware,
    SecurityHeadersMiddleware,
    get_client_ip,
)
from app.db.base import Base
from app.db.session import engine
from app.schemas.auth import TokenResponse, UserMeRead
from app.services import organization as organization_service
from app.services import user as user_service
from app.web._helpers import (
    authenticate_user,
    create_jwt,
    enforce_password_login_policy,
)
from app.web.auth import router as web_auth_router
from app.web.chat import router as web_chat_router
from app.web.pages import router as web_pages_router

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Register every model with Base.metadata so create_all sees them
# ---------------------------------------------------------------------------
from app.models import ai_call_log as _model_ai_call_log  # noqa: F401
from app.models import approval as _model_approval  # noqa: F401
from app.models import ceo_control as _model_ceo_control  # noqa: F401
from app.models import chat_message as _model_chat_message  # noqa: F401
from app.models import clone_control as _model_clone_control  # noqa: F401
from app.models import clone_performance as _model_clone_performance  # noqa: F401
from app.models import command as _model_command  # noqa: F401
from app.models import contact as _model_contact  # noqa: F401
from app.models import conversation as _model_conversation  # noqa: F401
from app.models import daily_plan as _model_daily_plan  # noqa: F401
from app.models import daily_run as _model_daily_run  # noqa: F401
from app.models import decision_log as _model_decision_log  # noqa: F401
from app.models import decision_trace as _model_decision_trace  # noqa: F401
from app.models import email as _model_email  # noqa: F401
from app.models import employee as _model_employee  # noqa: F401
from app.models import event as _model_event  # noqa: F401
from app.models import execution as _model_execution  # noqa: F401
from app.models import finance as _model_finance  # noqa: F401
from app.models import github as _model_github  # noqa: F401
from app.models import goal as _model_goal  # noqa: F401
from app.models import integration as _model_integration  # noqa: F401
from app.models import integration_signal as _model_integration_signal  # noqa: F401
from app.models import media_project as _model_media_project  # noqa: F401
from app.models import memory as _model_memory  # noqa: F401
from app.models import note as _model_note  # noqa: F401
from app.models import notification as _model_notification  # noqa: F401
from app.models import ops_metrics as _model_ops_metrics  # noqa: F401
from app.models import org_membership as _model_org_membership  # noqa: F401
from app.models import organization as _model_organization  # noqa: F401
from app.models import policy_rule as _model_policy_rule  # noqa: F401
from app.models import project as _model_project  # noqa: F401
from app.models import social as _model_social  # noqa: F401
from app.models import task as _model_task  # noqa: F401
from app.models import threat_signal as _model_threat_signal  # noqa: F401
from app.models import user as _model_user  # noqa: F401
from app.models import weekly_report as _model_weekly_report  # noqa: F401
from app.models import whatsapp_message as _model_whatsapp_message  # noqa: F401

# ---------------------------------------------------------------------------
# Startup safety guards
# ---------------------------------------------------------------------------
_UNSAFE_SECRET_KEYS = {"change_me_in_env", "changeme", "secret", "change-me", ""}
if settings.SECRET_KEY in _UNSAFE_SECRET_KEYS or len(settings.SECRET_KEY) < 32:
    raise RuntimeError(
        "SECRET_KEY is insecure. Set a 32+ character random value in .env. "
        'Generate one: python -c "import secrets; print(secrets.token_hex(32))"'
    )
_UNSAFE_PASSWORDS = {"demo", "password", "admin", "changeme", "change_me", ""}
if settings.ADMIN_PASSWORD in _UNSAFE_PASSWORDS or len(settings.ADMIN_PASSWORD) < 8:
    raise RuntimeError(
        "ADMIN_PASSWORD is insecure. Set a strong password (8+ chars) in .env."
    )
if settings.TOKEN_ENCRYPTION_KEY and settings.TOKEN_ENCRYPTION_KEY == settings.SECRET_KEY:
    raise RuntimeError(
        "TOKEN_ENCRYPTION_KEY must differ from SECRET_KEY for proper key separation. "
        'Generate a new one: python -c "import secrets; print(secrets.token_hex(32))"'
    )
if not settings.OAUTH_STATE_KEY:
    raise RuntimeError(
        "OAUTH_STATE_KEY must be set in .env for secure OAuth state signing. "
        "Using SECRET_KEY as fallback couples JWT and OAuth signing keys. "
        'Generate one: python -c "import secrets; print(secrets.token_hex(32))"'
    )
if settings.ENFORCE_STARTUP_VALIDATION or not settings.DEBUG:
    startup_issues = validate_startup_settings(settings)
    if startup_issues:
        raise RuntimeError(
            "Startup configuration validation failed:\n" + format_startup_issues(startup_issues)
        )


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
_server_start_time: float | None = None


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

    if settings.AUTO_CREATE_SCHEMA:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    if settings.AUTO_SEED_DEFAULTS:
        async with AsyncSession(engine) as db:
            org = await organization_service.ensure_default_organization(db)
            await user_service.ensure_default_user(db, organization_id=org.id)

    # Warn if session cookies are not secure (acceptable in dev, dangerous in prod)
    if not settings.COOKIE_SECURE and not settings.DEBUG:
        logger.warning(
            "COOKIE_SECURE=false in non-debug mode. Session cookies will be sent over HTTP. "
            "Set COOKIE_SECURE=true when running behind HTTPS."
        )

    # Warn if MFA is required by config but not yet enforced in code
    if settings.ACCOUNT_MFA_REQUIRED:
        logger.warning(
            "ACCOUNT_MFA_REQUIRED=true but TOTP enforcement is not implemented. "
            "Users can log in without MFA. Set ACCOUNT_MFA_REQUIRED=false or implement TOTP."
        )

    # Optional OpenTelemetry tracing (no-op when OTEL_EXPORTER_OTLP_ENDPOINT is unset)
    from app.core.telemetry import setup as setup_telemetry
    setup_telemetry(app=app)

    # Load dashboard-saved AI provider keys into in-memory cache
    from app.services.ai_router import load_ai_keys_from_db
    await load_ai_keys_from_db()

    from app.services.sync_scheduler import start_scheduler, stop_scheduler
    run_scheduler = settings.RUN_SCHEDULER
    if settings.SYNC_ENABLED and run_scheduler:
        start_scheduler(interval_minutes=settings.SYNC_INTERVAL_MINUTES)
    yield
    if settings.SYNC_ENABLED and run_scheduler:
        await stop_scheduler()
    await engine.dispose()


# ---------------------------------------------------------------------------
# App creation and middleware
# ---------------------------------------------------------------------------
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
    default_response_class=ORJSONResponse,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

_cors_origins = settings.cors_allowed_origins_list
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-CSRF-Token", "X-Correlation-ID"],
    )

# Middleware is applied in reverse order (last added = outermost = runs first).
# Desired execution order: SecurityHeaders → RequestLog → CorrelationID → RateLimit → BodyLimit → GZip
# So we add them bottom-up:
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(RequestBodyLimitMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(CorrelationIDMiddleware)
app.add_middleware(RequestLogMiddleware)
app.add_middleware(SecurityHeadersMiddleware)


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------
def _request_id_from_state(request: Request) -> str | None:
    return getattr(request.state, "correlation_id", None)


_STATUS_CODE_MAP = {
    400: "bad_request", 401: "unauthorized", 403: "forbidden",
    404: "not_found", 409: "conflict", 422: "validation_error", 429: "rate_limited",
}


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=error_envelope(
            code=_STATUS_CODE_MAP.get(exc.status_code, "http_error"),
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


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
    logger.warning("Database integrity violation: %s", type(exc.orig).__name__ if exc.orig else "unknown")
    return JSONResponse(
        status_code=409,
        content=error_envelope(
            code="conflict",
            detail="Resource already exists or constraint violation",
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


# ---------------------------------------------------------------------------
# Root-level endpoints (kept here because they're app-level, not web-specific)
# ---------------------------------------------------------------------------
@app.post("/token", response_model=TokenResponse)
async def login(
    request: Request,
    username: str = Form(..., min_length=3, max_length=254),
    password: str = Form(..., min_length=8, max_length=128),
    totp_code: str | None = Form(None, min_length=6, max_length=6),
    db: AsyncSession = Depends(get_db),
):
    enforce_password_login_policy()
    client_ip = get_client_ip(request)
    user = await authenticate_user(db, username, password, client_ip, "/token", totp_code=totp_code)
    return {"access_token": create_jwt(user), "token_type": "bearer"}


@app.get("/me", response_model=UserMeRead)
def me(user=Depends(get_current_api_user)):
    return {
        "email": user["email"],
        "id": user["id"],
        "role": user["role"],
        "org_id": user["org_id"],
    }


@app.get("/health")
async def health_check():
    import time

    from fastapi.responses import JSONResponse as _JSONResponse
    from sqlalchemy import text

    db_ok = True
    try:
        async with engine.connect() as conn:
            await asyncio.wait_for(conn.execute(text("SELECT 1")), timeout=3.0)
    except (SQLAlchemyError, TimeoutError) as exc:
        logger.warning("Health DB probe failed: %s", type(exc).__name__)
        db_ok = False

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


# ---------------------------------------------------------------------------
# Include routers
# ---------------------------------------------------------------------------
if settings.app_mode_normalized == "NIDIN_AI" or settings.app_mode_normalized == "EMPIREO_AI":
    app.include_router(api_router, prefix="/api/v1")
else:
    raise RuntimeError(f"Unsupported APP_MODE: {settings.APP_MODE!r}")

app.include_router(web_auth_router)
app.include_router(web_chat_router)
app.include_router(web_pages_router)
