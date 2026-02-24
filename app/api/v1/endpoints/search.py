"""Global search across tasks, notes, contacts, projects, goals, commands."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.models.task import Task
from app.models.note import Note
from app.models.contact import Contact
from app.models.project import Project
from app.models.goal import Goal
from app.models.command import Command

router = APIRouter(prefix="/search", tags=["search"])

MAX_PER_TYPE = 5


@router.get("")
async def global_search(
    q: str = Query(..., min_length=1, max_length=200),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    """
    Search across all data types. Returns up to 5 results per type.
    Uses LIKE matching (case-insensitive for SQLite, depends on collation for PG).
    """
    org_id = int(actor.get("org_id", 1))
    pattern = f"%{q}%"

    from sqlalchemy import select

    # Tasks
    tasks_q = await db.execute(
        select(Task.id, Task.title, Task.category, Task.is_done)
        .where(Task.organization_id == org_id)
        .where(or_(Task.title.ilike(pattern), Task.description.ilike(pattern)))
        .order_by(Task.created_at.desc())
        .limit(MAX_PER_TYPE)
    )
    tasks = [{"id": r.id, "title": r.title, "category": r.category, "done": r.is_done, "type": "task"} for r in tasks_q]

    # Notes
    notes_q = await db.execute(
        select(Note.id, Note.title, Note.content)
        .where(Note.organization_id == org_id)
        .where(or_(Note.title.ilike(pattern), Note.content.ilike(pattern)))
        .order_by(Note.created_at.desc())
        .limit(MAX_PER_TYPE)
    )
    notes = [{"id": r.id, "title": r.title or r.content[:60], "type": "note"} for r in notes_q]

    # Contacts
    contacts_q = await db.execute(
        select(Contact.id, Contact.name, Contact.email, Contact.relationship)
        .where(Contact.organization_id == org_id)
        .where(or_(Contact.name.ilike(pattern), Contact.email.ilike(pattern)))
        .order_by(Contact.name)
        .limit(MAX_PER_TYPE)
    )
    contacts = [{"id": r.id, "title": r.name, "email": r.email, "relationship": r.relationship, "type": "contact"} for r in contacts_q]

    # Projects
    projects_q = await db.execute(
        select(Project.id, Project.title, Project.status)
        .where(Project.organization_id == org_id)
        .where(Project.title.ilike(pattern))
        .order_by(Project.created_at.desc())
        .limit(MAX_PER_TYPE)
    )
    projects = [{"id": r.id, "title": r.title, "status": r.status, "type": "project"} for r in projects_q]

    # Goals
    goals_q = await db.execute(
        select(Goal.id, Goal.title, Goal.status)
        .where(Goal.organization_id == org_id)
        .where(Goal.title.ilike(pattern))
        .order_by(Goal.created_at.desc())
        .limit(MAX_PER_TYPE)
    )
    goals = [{"id": r.id, "title": r.title, "status": r.status, "type": "goal"} for r in goals_q]

    # Commands
    commands_q = await db.execute(
        select(Command.id, Command.command_text)
        .where(Command.organization_id == org_id)
        .where(Command.command_text.ilike(pattern))
        .order_by(Command.created_at.desc())
        .limit(MAX_PER_TYPE)
    )
    commands = [{"id": r.id, "title": r.command_text[:80], "type": "command"} for r in commands_q]

    results = tasks + notes + contacts + projects + goals + commands
    return {
        "query": q,
        "total": len(results),
        "results": results,
    }
