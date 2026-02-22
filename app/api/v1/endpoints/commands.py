from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.schemas.command import CommandCreate, CommandRead
from app.services import command as command_service

router = APIRouter(prefix="/commands", tags=["Commands"])


@router.post("", response_model=CommandRead, status_code=201)
async def create_command(
    data: CommandCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF")),
) -> CommandRead:
    """Log a new command and its AI response."""
    return await command_service.create_command(db, data, organization_id=actor["org_id"])


@router.get("", response_model=list[CommandRead])
async def list_commands(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF")),
) -> list[CommandRead]:
    """Return the 50 most recent commands, newest first."""
    return await command_service.list_commands(db, organization_id=actor["org_id"])
