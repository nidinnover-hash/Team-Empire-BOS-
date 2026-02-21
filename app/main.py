from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.deps import get_db
from app.db.base import Base
from app.db.session import engine
from app.services import command as command_service
from app.services import contact as contact_service
from app.services import finance as finance_service
from app.services import goal as goal_service
from app.services import note as note_service
from app.services import project as project_service
from app.services import task as task_service

# Register every model with Base.metadata so create_all sees them
import app.models.command  # noqa: F401
import app.models.task     # noqa: F401
import app.models.note     # noqa: F401
import app.models.project  # noqa: F401
import app.models.goal     # noqa: F401
import app.models.contact  # noqa: F401
import app.models.finance  # noqa: F401

templates = Jinja2Templates(directory="app/templates")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Dev convenience: auto-create all tables on startup
    # In production: delete personal_clone.db and run: alembic upgrade head
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.include_router(api_router, prefix="/api/v1")


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    commands  = await command_service.list_commands(db, limit=10)
    tasks     = await task_service.list_tasks(db, limit=20, is_done=False)
    notes     = await note_service.list_notes(db, limit=10)
    projects  = await project_service.list_projects(db, limit=10)
    goals     = await goal_service.list_goals(db, limit=10)
    contacts  = await contact_service.list_contacts(db, limit=8)
    finance   = await finance_service.get_summary(db)

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request":  request,
            "commands": commands,
            "tasks":    tasks,
            "notes":    notes,
            "projects": projects,
            "goals":    goals,
            "contacts": contacts,
            "finance":  finance,
        },
    )
