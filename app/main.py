from contextlib import asynccontextmanager
import secrets
from typing import AsyncGenerator

from fastapi import Depends, FastAPI, Form, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.router import api_router
from app.api.v1.endpoints.ops import run_daily_run_workflow
from app.core.config import settings

# ── Startup safety guard ──────────────────────────────────────────────────────
_UNSAFE_SECRET_KEYS = {"change_me_in_env", "changeme", "secret", "change-me", ""}
if settings.SECRET_KEY in _UNSAFE_SECRET_KEYS or len(settings.SECRET_KEY) < 32:
    raise RuntimeError(
        "SECRET_KEY is insecure. Set a 32+ character random value in .env. "
        "Generate one: python -c \"import secrets; print(secrets.token_hex(32))\""
    )
from app.core.deps import get_current_web_user, get_db, verify_csrf
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
import app.models.command  # noqa: F401
import app.models.task  # noqa: F401
import app.models.note  # noqa: F401
import app.models.project  # noqa: F401
import app.models.goal  # noqa: F401
import app.models.contact  # noqa: F401
import app.models.finance  # noqa: F401
import app.models.event  # noqa: F401
import app.models.user  # noqa: F401
import app.models.approval  # noqa: F401
import app.models.organization  # noqa: F401
import app.models.execution  # noqa: F401
import app.models.integration  # noqa: F401
import app.models.memory  # noqa: F401
import app.models.email  # noqa: F401
import app.models.daily_run  # noqa: F401

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


from app.core.middleware import CorrelationIDMiddleware

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)
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
        secure=False,
        path="/",
    )
    response.set_cookie(
        key="pc_csrf",
        value=csrf_token,
        max_age=max_age,
        httponly=False,
        samesite="lax",
        secure=False,
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
