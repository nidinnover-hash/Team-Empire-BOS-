"""
Memory service — manages profile memory, team members, and daily context.

The most important function here is build_memory_context() which assembles
everything into a single string that gets injected into every AI call.
"""

from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import DailyContext, ProfileMemory, TeamMember
from app.schemas.memory import (
    DailyContextCreate,
    TeamMemberCreate,
    TeamMemberUpdate,
)


# ── Profile Memory ────────────────────────────────────────────────────────────

async def get_profile_memory(
    db: AsyncSession, organization_id: int
) -> list[ProfileMemory]:
    result = await db.execute(
        select(ProfileMemory)
        .where(ProfileMemory.organization_id == organization_id)
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
    """Create or update a profile memory entry by key."""
    result = await db.execute(
        select(ProfileMemory).where(
            ProfileMemory.organization_id == organization_id,
            ProfileMemory.key == key,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.value = value
        existing.category = category
        existing.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(existing)
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
    await db.commit()
    await db.refresh(new_entry)
    return new_entry


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
        query = query.where(TeamMember.is_active == True)  # noqa: E712
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
    return result.scalar_one_or_none()


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

async def build_memory_context(db: AsyncSession, organization_id: int) -> str:
    """
    Assemble all memory into a single string for AI injection.

    This is what makes the clone feel like Nidin — it knows who he is,
    who his team is, and what's happening today.
    """
    lines: list[str] = []

    # Profile memory
    profile = await get_profile_memory(db, organization_id=organization_id)
    if profile:
        lines.append("PROFILE:")
        for entry in profile:
            lines.append(f"  - {entry.key}: {entry.value}")
        lines.append("")

    # Team members grouped by team
    members = await get_team_members(db, organization_id=organization_id, active_only=True)
    if members:
        teams: dict[str, list[TeamMember]] = {}
        for m in members:
            key = m.team or "general"
            teams.setdefault(key, []).append(m)

        for team_name, team_members in sorted(teams.items()):
            lines.append(f"TEAM ({team_name}):")
            for m in team_members:
                ai_label = ["", "no AI", "basic AI", "intermediate AI", "advanced AI", "AI expert"][m.ai_level]
                project = f" | Project: {m.current_project}" if m.current_project else ""
                lines.append(
                    f"  - {m.name} | {m.role_title or 'Staff'} | {ai_label}{project}"
                )
        lines.append("")

    # Today's context
    today_context = await get_daily_context(
        db,
        organization_id=organization_id,
        for_date=date.today(),
    )
    if today_context:
        lines.append("TODAY'S CONTEXT:")
        for ctx in today_context:
            related = f" (re: {ctx.related_to})" if ctx.related_to else ""
            lines.append(f"  [{ctx.context_type.upper()}] {ctx.content}{related}")
        lines.append("")

    if not lines:
        return ""

    return "\n".join(lines)
