from contextlib import asynccontextmanager
import secrets
from typing import AsyncGenerator

from fastapi import Depends, FastAPI, Form, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.router import api_router
from app.api.v1.endpoints.ops import run_daily_run_workflow
from app.core.config import settings, validate_startup_settings
from app.core.deps import get_current_web_user, get_db, verify_csrf
from app.core.middleware import CorrelationIDMiddleware, RateLimitMiddleware
from app.core.security import create_access_token, decode_access_token, get_current_user, verify_password
from app.db.base import Base
from app.db.session import engine
from app.services import command as command_service
from app.services import contact as contact_service
from app.services import finance as finance_service
from app.services import briefing as briefing_service
from app.services import goal as goal_service
from app.services import note as note_service
from app.services import organization as organization_service
from app.services import project as project_service
from app.services import task as task_service
from app.services import user as user_service

# Register every model with Base.metadata so create_all sees them
from app.models import approval as _model_approval  # noqa: F401
from app.models import command as _model_command  # noqa: F401
from app.models import contact as _model_contact  # noqa: F401
from app.models import daily_run as _model_daily_run  # noqa: F401
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

# Startup safety guard
_UNSAFE_SECRET_KEYS = {"change_me_in_env", "changeme", "secret", "change-me", ""}
if settings.SECRET_KEY in _UNSAFE_SECRET_KEYS or len(settings.SECRET_KEY) < 32:
    raise RuntimeError(
        "SECRET_KEY is insecure. Set a 32+ character random value in .env. "
        "Generate one: python -c \"import secrets; print(secrets.token_hex(32))\""
    )
if settings.ENFORCE_STARTUP_VALIDATION:
    startup_issues = validate_startup_settings(settings)
    if startup_issues:
        raise RuntimeError(
            "Startup configuration validation failed: " + "; ".join(startup_issues)
        )

templates = Jinja2Templates(directory="app/templates")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Production should use migrations only; optional auto-create/seed for local dev.
    if settings.AUTO_CREATE_SCHEMA:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    if settings.AUTO_SEED_DEFAULTS:
        async with AsyncSession(engine) as db:
            org = await organization_service.ensure_default_organization(db)
            await user_service.ensure_default_user(db, organization_id=org.id)
    yield
    await engine.dispose()

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)
# Middleware is applied in reverse order - CorrelationID wraps RateLimit
app.add_middleware(RateLimitMiddleware)
app.add_middleware(CorrelationIDMiddleware)


@app.post("/token")
async def login(
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    user = await user_service.get_user_by_email(db, username)
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
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
    return {"access_token": access_token, "token_type": "bearer"}


@app.get("/web/login", response_class=HTMLResponse, include_in_schema=False)
async def web_login_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "login.html", {"request": request, "error": None})


@app.post("/web/login")
async def web_login(
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await user_service.get_user_by_email(db, username)
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
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
    return {"status": "ok", "email": user.email, "role": user.role}


@app.post("/web/logout")
async def web_logout(response: Response) -> dict:
    response.delete_cookie("pc_session", path="/")
    response.delete_cookie("pc_csrf", path="/")
    return {"status": "logged_out"}


@app.get("/web/session")
async def web_session(request: Request) -> dict:
    token = request.cookies.get("pc_session")
    if not token:
        return {"logged_in": False}
    try:
        payload = decode_access_token(token)
    except Exception:
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

    org_id = int(user["org_id"])
    memory_context = await build_memory_context(db, organization_id=org_id)
    result = await run_agent(
        request=AgentChatRequest(
            message=message,
            force_role=force_role if force_role else None,
        ),
        memory_context=memory_context,
    )
    return JSONResponse(content={
        "role": result.role,
        "response": result.response,
        "requires_approval": result.requires_approval,
        "proposed_actions_count": len(result.proposed_actions),
    })


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


app.include_router(api_router, prefix="/api/v1")


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
        except Exception:
            user = None
    if user is None:
        return RedirectResponse(url="/web/login", status_code=302)
    org_id = int(user["org_id"])

    commands = await command_service.list_commands(db, limit=10, organization_id=org_id)
    tasks = await task_service.list_tasks(db, limit=20, is_done=False, organization_id=org_id)
    notes = await note_service.list_notes(db, limit=10, organization_id=org_id)
    projects = await project_service.list_projects(db, limit=10, organization_id=org_id)
    goals = await goal_service.list_goals(db, limit=10, organization_id=org_id)
    contacts = await contact_service.list_contacts(db, limit=8, organization_id=org_id)
    finance = await finance_service.get_summary(db, organization_id=org_id)
    executive = await briefing_service.get_executive_briefing(db, org_id=org_id)

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
            "executive": executive,
            "session_user": user,
        },
    )


