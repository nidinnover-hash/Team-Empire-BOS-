"""CEO Orchestrator — cross-workspace intelligence endpoints."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.schemas.orchestrator import OrchestratorBriefing, WorkspaceHealth
from app.services import orchestrator as orch_service
from app.services.workspace import get_workspace

router = APIRouter(prefix="/orchestrator", tags=["CEO Orchestrator"])


@router.get("/briefing", response_model=OrchestratorBriefing)
async def get_ceo_briefing(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> OrchestratorBriefing:
    """Generate a CEO-level briefing across all workspace brains."""
    return await orch_service.generate_briefing(db, org_id=int(user["org_id"]))


@router.get("/workspace-health/{workspace_id}", response_model=WorkspaceHealth)
async def get_workspace_health(
    workspace_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> WorkspaceHealth:
    """Get health score for a specific workspace brain."""
    org_id = int(user["org_id"])
    ws = await get_workspace(db, org_id=org_id, workspace_id=workspace_id)
    if not ws:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Workspace not found")
    return await orch_service.compute_workspace_health(db, org_id, ws)
