from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.schemas.persona import PersonaDashboard
from app.services import persona as persona_service

router = APIRouter(prefix="/personas", tags=["Personas"])


@router.get("/dashboard", response_model=PersonaDashboard)
async def get_persona_dashboard(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> PersonaDashboard:
    """AI workforce readiness dashboard — aggregated clone persona view."""
    return await persona_service.get_persona_dashboard(db, organization_id=actor["org_id"])
