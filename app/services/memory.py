"""
Memory service — manages profile memory, team members, and daily context.

The most important function here is build_memory_context() which assembles
everything into a single string that gets injected into every AI call.
"""

from collections.abc import Mapping
from typing import cast

from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import DailyContext, ProfileMemory, TeamMember
from app.schemas.memory import (
    DailyContextCreate,
    TeamMemberCreate,
    TeamMemberUpdate,
)
from app.memory.retrieval import (
    DEFAULT_CONTEXT_CHAR_LIMIT,
    build_focused_context,
    build_typed_context,
)


# ── Profile Memory ────────────────────────────────────────────────────────────

async def get_profile_memory(
    db: AsyncSession, organization_id: int
) -> list[ProfileMemory]:
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(ProfileMemory)
        .where(
            ProfileMemory.organization_id == organization_id,
            (ProfileMemory.expires_at.is_(None)) | (ProfileMemory.expires_at > now),
        )
        .order_by(ProfileMemory.category, ProfileMemory.key)
    )
    return list(result.scalars().all())


async def upsert_profile_memory(
    db: AsyncSession,
    organization_id: int,
    key: str,
    value: str,
    category: str | None = None,
) -> ProfileMemory:
    """Create or update a profile memory entry by key.

    Handles the TOCTOU race: if two concurrent calls both pass the SELECT,
    the INSERT that loses gets an IntegrityError and retries as an UPDATE.
    """
    result = await db.execute(
        select(ProfileMemory).where(
            ProfileMemory.organization_id == organization_id,
            ProfileMemory.key == key,
        )
    )
    existing = cast(ProfileMemory | None, result.scalar_one_or_none())

    if existing:
        existing.value = value
        existing.category = category
        existing.updated_at = datetime.now(timezone.utc)
        try:
            await db.commit()
            await db.refresh(existing)
        except Exception:
            await db.rollback()
            raise
        return existing

    new_entry = ProfileMemory(
        organization_id=organization_id,
        key=key,
        value=value,
        category=category,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(new_entry)
    try:
        await db.commit()
        await db.refresh(new_entry)
    except IntegrityError:
        # Concurrent insert won the race — retry as update
        await db.rollback()
        retry = await db.execute(
            select(ProfileMemory).where(
                ProfileMemory.organization_id == organization_id,
                ProfileMemory.key == key,
            )
        )
        existing = cast(ProfileMemory, retry.scalar_one())
        existing.value = value
        existing.category = category
        existing.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(existing)
        return existing
    except Exception:
        await db.rollback()
        raise
    return new_entry


async def delete_profile_memory(
    db: AsyncSession, entry_id: int, organization_id: int
) -> bool:
    """Delete a profile memory entry by ID. Returns True if it existed and was deleted."""
    result = await db.execute(
        select(ProfileMemory).where(
            ProfileMemory.id == entry_id,
            ProfileMemory.organization_id == organization_id,
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        return False
    await db.delete(entry)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return True


# ── Team Members ──────────────────────────────────────────────────────────────

async def get_team_members(
    db: AsyncSession,
    organization_id: int,
    team: str | None = None,
    active_only: bool = True,
) -> list[TeamMember]:
    query = select(TeamMember).where(TeamMember.organization_id == organization_id)
    if team:
        query = query.where(TeamMember.team == team)
    if active_only:
        query = query.where(TeamMember.is_active.is_(True))
    query = query.order_by(TeamMember.team, TeamMember.name)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_team_member(
    db: AsyncSession, member_id: int, organization_id: int
) -> TeamMember | None:
    result = await db.execute(
        select(TeamMember).where(
            TeamMember.id == member_id,
            TeamMember.organization_id == organization_id,
        )
    )
    return cast(TeamMember | None, result.scalar_one_or_none())


async def create_team_member(
    db: AsyncSession, data: TeamMemberCreate, organization_id: int
) -> TeamMember:
    member = TeamMember(
        organization_id=organization_id,
        name=data.name,
        role_title=data.role_title,
        team=data.team,
        reports_to_id=data.reports_to_id,
        skills=data.skills,
        ai_level=data.ai_level,
        current_project=data.current_project,
        notes=data.notes,
        user_id=data.user_id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(member)
    await db.commit()
    await db.refresh(member)
    return member


async def update_team_member(
    db: AsyncSession,
    member_id: int,
    organization_id: int,
    data: TeamMemberUpdate,
) -> TeamMember | None:
    member = await get_team_member(db, member_id, organization_id)
    if not member:
        return None
    for field, val in data.model_dump(exclude_unset=True).items():
        setattr(member, field, val)
    await db.commit()
    await db.refresh(member)
    return member


# ── Daily Context ─────────────────────────────────────────────────────────────

async def get_daily_context(
    db: AsyncSession,
    organization_id: int,
    for_date: date | None = None,
) -> list[DailyContext]:
    target = for_date or date.today()
    result = await db.execute(
        select(DailyContext)
        .where(
            DailyContext.organization_id == organization_id,
            DailyContext.date == target,
        )
        .order_by(DailyContext.context_type, DailyContext.created_at)
    )
    return list(result.scalars().all())


async def add_daily_context(
    db: AsyncSession, data: DailyContextCreate, organization_id: int
) -> DailyContext:
    entry = DailyContext(
        organization_id=organization_id,
        date=data.date,
        context_type=data.context_type,
        content=data.content,
        related_to=data.related_to,
        created_at=datetime.now(timezone.utc),
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


# ── Memory Context Builder ────────────────────────────────────────────────────

async def build_memory_context(
    db: AsyncSession,
    organization_id: int,
    categories: list[str] | None = None,
    char_limit: int = DEFAULT_CONTEXT_CHAR_LIMIT,
) -> str:
    """
    Assemble memory into a trimmed string for AI injection.

    Uses build_focused_context() from app/memory/retrieval.py to:
    - Optionally filter profile entries by category
    - Automatically trim to char_limit to prevent context bloat

    This is what makes the clone feel like Nidin — it knows who he is,
    who his team is, and what's happening today.
    """
    import asyncio as _asyncio
    from sqlalchemy import select as _select
    from app.models.task import Task as _Task
    from app.services.integration import list_integrations as _list_integrations

    profile, members, today_context, integrations = await _asyncio.gather(
        get_profile_memory(db, organization_id=organization_id),
        get_team_members(db, organization_id=organization_id, active_only=True),
        get_daily_context(db, organization_id=organization_id, for_date=date.today()),
        _list_integrations(db, organization_id=organization_id),
    )
    integration_statuses: list[Mapping[str, object]] = [
        {
            "type": item.type,
            "status": item.status,
            "last_sync_at": item.last_sync_at.isoformat() if item.last_sync_at else None,
        }
        for item in integrations
    ]

    base_context = build_focused_context(
        profile_entries=profile,
        team_members=members,
        daily_contexts=today_context,
        categories=categories,
        char_limit=char_limit,
    )

    # Reuse typed context assembly so integration layer stays populated in live AI flows.
    typed_layers = build_typed_context(
        profile_entries=profile,
        team_members=members,
        daily_contexts=today_context,
        integration_statuses=integration_statuses,
        categories=categories,
        char_limit=char_limit,
    )
    integration_layer = next((layer for layer in typed_layers if layer.get("layer_type") == "integration"), None)
    if integration_layer and integration_layer.get("content"):
        integration_block = str(integration_layer["content"])
        remaining = char_limit - len(base_context)
        if remaining > 100:
            base_context = base_context + "\n\n" + integration_block[:remaining]

    # Single query for all external tasks (ClickUp + GitHub PRs + GitHub issues)
    ext_result = await db.execute(
        _select(_Task).where(
            _Task.organization_id == organization_id,
            _Task.external_source.in_(["clickup", "github_pr", "github_issue"]),
            _Task.is_done.is_(False),
        ).order_by(_Task.priority.desc()).limit(45)
    )
    ext_tasks = list(ext_result.scalars().all())

    cu_tasks = [t for t in ext_tasks if t.external_source == "clickup"][:20]
    gh_prs = [t for t in ext_tasks if t.external_source == "github_pr"][:15]
    gh_issues = [t for t in ext_tasks if t.external_source == "github_issue"][:10]

    if cu_tasks:
        lines = ["[CLICKUP OPEN TASKS]"]
        for t in cu_tasks:
            due = f" (due {t.due_date})" if t.due_date else ""
            lines.append(f"- {t.title}{due}")
        lines.append("[END CLICKUP TASKS]")
        clickup_block = "\n".join(lines)
        remaining = char_limit - len(base_context)
        if remaining > 100:
            base_context = base_context + "\n\n" + clickup_block[:remaining]

    if gh_prs or gh_issues:
        lines = ["[GITHUB DEV ACTIVITY]"]
        if gh_prs:
            lines.append(f"Open PRs ({len(gh_prs)}):")
            for t in gh_prs:
                lines.append(f"  • {t.title}")
        if gh_issues:
            lines.append(f"Open bug issues ({len(gh_issues)}):")
            for t in gh_issues:
                lines.append(f"  • {t.title}")
        lines.append("[END GITHUB]")
        github_block = "\n".join(lines)
        remaining = char_limit - len(base_context)
        if remaining > 100:
            base_context = base_context + "\n\n" + github_block[:remaining]

    # ── Work pattern feedback loop ──
    # Inject ops intelligence patterns so the AI reasons about real work data.
    from app.services.pattern_analysis import build_work_patterns_context
    try:
        patterns_block = await build_work_patterns_context(db, organization_id, weeks=2)
        if patterns_block:
            remaining = char_limit - len(base_context)
            if remaining > 200:
                base_context = base_context + "\n\n" + patterns_block[:remaining]
    except Exception:
        pass  # Graceful degradation — patterns are supplementary

    return base_context
