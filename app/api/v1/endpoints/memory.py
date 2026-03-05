from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.logs.audit import record_action
from app.schemas.memory import (
    DailyContextCreate,
    DailyContextRead,
    ProfileMemoryCreate,
    ProfileMemoryRead,
    TeamMemberCreate,
    TeamMemberRead,
    TeamMemberUpdate,
)
from app.services import memory as memory_service

router = APIRouter(prefix="/memory", tags=["Memory"])


# ── Profile Memory ────────────────────────────────────────────────────────────

@router.get("/profile", response_model=list[ProfileMemoryRead])
async def list_profile_memory(
    workspace_id: int | None = Query(None, description="Scope to workspace"),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO")),
) -> list[ProfileMemoryRead]:
    """List all profile memory entries. CEO only."""
    return await memory_service.get_profile_memory(
        db,
        organization_id=int(user["org_id"]),
        workspace_id=workspace_id,
    )


@router.post("/profile", response_model=ProfileMemoryRead, status_code=201)
async def set_profile_memory(
    data: ProfileMemoryCreate,
    workspace_id: int | None = Query(None, description="Scope to workspace"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles("CEO")),
) -> ProfileMemoryRead:
    """Add or update a profile memory entry. CEO only."""
    org_id = int(current_user["org_id"])
    entry = await memory_service.upsert_profile_memory(
        db,
        organization_id=org_id,
        key=data.key,
        value=data.value,
        category=data.category,
        workspace_id=workspace_id,
    )
    await record_action(
        db=db,
        event_type="profile_memory_updated",
        actor_user_id=int(current_user["id"]),
        entity_type="profile_memory",
        entity_id=entry.id,
        payload_json={"key": data.key, "category": data.category},
        organization_id=org_id,
    )
    return entry


@router.delete("/profile/{entry_id}", status_code=204)
async def delete_profile_memory(
    entry_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles("CEO")),
) -> None:
    """Delete a profile memory entry by ID. CEO only."""
    org_id = int(current_user["org_id"])
    deleted = await memory_service.delete_profile_memory(
        db, entry_id=entry_id, organization_id=org_id
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory entry not found")
    await record_action(
        db=db,
        event_type="profile_memory_deleted",
        actor_user_id=int(current_user["id"]),
        entity_type="profile_memory",
        entity_id=entry_id,
        payload_json={"entry_id": entry_id},
        organization_id=org_id,
    )


# ── Team Members ──────────────────────────────────────────────────────────────

@router.get("/team", response_model=list[TeamMemberRead])
async def list_team_members(
    team: str | None = Query(None, max_length=50),
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list[TeamMemberRead]:
    """List team members. Filter by team name (tech, sales, ops, admin)."""
    return await memory_service.get_team_members(
        db,
            organization_id=int(_user["org_id"]),
        team=team,
    )


@router.post("/team", response_model=TeamMemberRead, status_code=201)
async def add_team_member(
    data: TeamMemberCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> TeamMemberRead:
    """Add a new team member. ADMIN+ only."""
    org_id = int(current_user["org_id"])
    member = await memory_service.create_team_member(
        db,
        data,
        organization_id=org_id,
    )
    await record_action(
        db=db,
        event_type="team_member_created",
        actor_user_id=int(current_user["id"]),
        entity_type="team_member",
        entity_id=member.id,
        payload_json={"name": member.name, "team": member.team, "role_title": member.role_title},
        organization_id=org_id,
    )
    return member


@router.patch("/team/{member_id}", response_model=TeamMemberRead)
async def update_team_member(
    member_id: int,
    data: TeamMemberUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> TeamMemberRead:
    """Update a team member's profile. ADMIN+ only."""
    org_id = int(current_user["org_id"])
    member = await memory_service.update_team_member(
        db,
        member_id,
        organization_id=org_id,
        data=data,
    )
    if not member:
        raise HTTPException(status_code=404, detail="Team member not found")
    await record_action(
        db=db,
        event_type="team_member_updated",
        actor_user_id=int(current_user["id"]),
        entity_type="team_member",
        entity_id=member.id,
        payload_json=data.model_dump(exclude_unset=True),
        organization_id=org_id,
    )
    return member


# ── Daily Context ─────────────────────────────────────────────────────────────

@router.get("/context", response_model=list[DailyContextRead])
async def get_daily_context(
    for_date: date | None = None,
    workspace_id: int | None = Query(None, description="Scope to workspace"),
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list[DailyContextRead]:
    """Get today's context entries (priorities, meetings, blockers, decisions)."""
    return await memory_service.get_daily_context(
        db,
        organization_id=int(_user["org_id"]),
        for_date=for_date,
        workspace_id=workspace_id,
    )


@router.post("/context", response_model=DailyContextRead, status_code=201)
async def add_daily_context(
    data: DailyContextCreate,
    workspace_id: int | None = Query(None, description="Scope to workspace"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> DailyContextRead:
    """Add a context item for today (priority, meeting, blocker, or decision)."""
    org_id = int(current_user["org_id"])
    entry = await memory_service.add_daily_context(
        db,
        data,
        organization_id=org_id,
        workspace_id=workspace_id,
    )
    await record_action(
        db=db,
        event_type="daily_context_added",
        actor_user_id=int(current_user["id"]),
        entity_type="daily_context",
        entity_id=entry.id,
        payload_json={"type": data.context_type, "related_to": data.related_to},
        organization_id=org_id,
    )
    return entry
