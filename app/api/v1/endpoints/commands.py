from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_workspace_id, get_db
from app.core.rbac import require_roles
from app.schemas.command import CommandCreate, CommandRead
from app.services import command as command_service

router = APIRouter(prefix="/commands", tags=["Commands"])


@router.post("", response_model=CommandRead, status_code=201)
async def create_command(
    data: CommandCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF")),
    workspace_id: int = Depends(get_current_workspace_id),
) -> CommandRead:
    """Log a new command and its AI response."""
    return await command_service.create_command(
        db,
        data,
        organization_id=actor["org_id"],
        actor_user_id=int(actor["id"]),
        actor_role=str(actor["role"]),
    )


@router.get("", response_model=list[CommandRead])
async def list_commands(
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF")),
    workspace_id: int = Depends(get_current_workspace_id),
) -> list[CommandRead]:
    """Return recent commands, newest first."""
    return await command_service.list_commands(db, limit=limit, organization_id=actor["org_id"])
