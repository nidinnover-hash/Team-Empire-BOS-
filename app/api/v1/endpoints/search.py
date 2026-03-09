"""Unified global search across tasks, notes, contacts, projects, goals, deals, finance, commands."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.models.command import Command
from app.models.contact import Contact
from app.models.deal import Deal
from app.models.finance import FinanceEntry
from app.models.goal import Goal
from app.models.note import Note
from app.models.project import Project
from app.models.task import Task
from app.schemas.search import SearchResponse

router = APIRouter(prefix="/search", tags=["search"])

MAX_PER_TYPE = 5


@router.get("", response_model=SearchResponse)
async def global_search(
    q: str = Query(..., min_length=1, max_length=200),
    types: str | None = Query(None, max_length=200, description="Comma-separated entity types to search"),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    """
    Unified search across all data types. Returns up to 5 results per type.
    Optionally filter by type: ?types=task,contact,deal
    """
    org_id = int(actor["org_id"])
    pattern = f"%{q}%"
    allowed_types = set(types.split(",")) if types else None
    results = []

    def _want(t: str) -> bool:
        return allowed_types is None or t in allowed_types

    # Tasks
    if _want("task"):
        rows = await db.execute(
            select(Task.id, Task.title, Task.category, Task.is_done)
            .where(Task.organization_id == org_id)
            .where(or_(Task.title.ilike(pattern), Task.description.ilike(pattern)))
            .order_by(Task.created_at.desc()).limit(MAX_PER_TYPE)
        )
        results.extend(
            {"id": r.id, "title": r.title, "category": r.category, "done": r.is_done, "type": "task"}
            for r in rows
        )

    # Notes
    if _want("note"):
        rows = await db.execute(
            select(Note.id, Note.title, Note.content)
            .where(Note.organization_id == org_id)
            .where(or_(Note.title.ilike(pattern), Note.content.ilike(pattern)))
            .order_by(Note.created_at.desc()).limit(MAX_PER_TYPE)
        )
        results.extend(
            {"id": r.id, "title": r.title or r.content[:60], "type": "note"}
            for r in rows
        )

    # Contacts
    if _want("contact"):
        rows = await db.execute(
            select(Contact.id, Contact.name, Contact.email, Contact.relationship)
            .where(Contact.organization_id == org_id)
            .where(or_(Contact.name.ilike(pattern), Contact.email.ilike(pattern), Contact.company.ilike(pattern)))
            .order_by(Contact.name).limit(MAX_PER_TYPE)
        )
        results.extend(
            {"id": r.id, "title": r.name, "email": r.email, "relationship": r.relationship, "type": "contact"}
            for r in rows
        )

    # Projects
    if _want("project"):
        rows = await db.execute(
            select(Project.id, Project.title, Project.status)
            .where(Project.organization_id == org_id)
            .where(Project.title.ilike(pattern))
            .order_by(Project.created_at.desc()).limit(MAX_PER_TYPE)
        )
        results.extend(
            {"id": r.id, "title": r.title, "status": r.status, "type": "project"}
            for r in rows
        )

    # Goals
    if _want("goal"):
        rows = await db.execute(
            select(Goal.id, Goal.title, Goal.status)
            .where(Goal.organization_id == org_id)
            .where(Goal.title.ilike(pattern))
            .order_by(Goal.created_at.desc()).limit(MAX_PER_TYPE)
        )
        results.extend(
            {"id": r.id, "title": r.title, "status": r.status, "type": "goal"}
            for r in rows
        )

    # Deals
    if _want("deal"):
        rows = await db.execute(
            select(Deal.id, Deal.title, Deal.stage, Deal.value)
            .where(Deal.organization_id == org_id)
            .where(or_(Deal.title.ilike(pattern), Deal.description.ilike(pattern)))
            .order_by(Deal.updated_at.desc()).limit(MAX_PER_TYPE)
        )
        results.extend(
            {"id": r.id, "title": r.title, "status": r.stage, "type": "deal"}
            for r in rows
        )

    # Finance entries
    if _want("finance"):
        rows = await db.execute(
            select(FinanceEntry.id, FinanceEntry.description, FinanceEntry.category, FinanceEntry.type)
            .where(FinanceEntry.organization_id == org_id)
            .where(or_(FinanceEntry.description.ilike(pattern), FinanceEntry.category.ilike(pattern)))
            .order_by(FinanceEntry.entry_date.desc()).limit(MAX_PER_TYPE)
        )
        results.extend(
            {"id": r.id, "title": (r.description or r.category)[:80], "category": r.category, "type": "finance"}
            for r in rows
        )

    # Commands
    if _want("command"):
        rows = await db.execute(
            select(Command.id, Command.command_text)
            .where(Command.organization_id == org_id)
            .where(Command.command_text.ilike(pattern))
            .order_by(Command.created_at.desc()).limit(MAX_PER_TYPE)
        )
        results.extend(
            {"id": r.id, "title": r.command_text[:80], "type": "command"}
            for r in rows
        )

    return {
        "query": q,
        "total": len(results),
        "results": results,
    }
