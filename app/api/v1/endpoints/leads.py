"""Lead ingest and machine-facing lead APIs."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_api_user, get_db
from app.core.lead_routing import EMPIRE_DIGITAL_COMPANY_ID
from app.schemas.lead_ingest import SocialLeadIngestRequest, SocialLeadIngestResponse
from app.services import social_ingest as social_ingest_service

router = APIRouter(prefix="/leads", tags=["Leads"])


@router.post("/ingest-social", response_model=SocialLeadIngestResponse, status_code=status.HTTP_201_CREATED)
async def ingest_social_lead(
    body: SocialLeadIngestRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(get_current_api_user),
) -> SocialLeadIngestResponse:
    """
    Ingest a single lead from a social platform (FB, IG, LinkedIn, etc.).
    Creates or merges a contact in the Empire Digital org, runs lead routing, and emits lead.created_from_social.
    Caller must be authenticated (JWT or API key) and belong to the Empire Digital organization.
    """
    org_id = int(actor["org_id"])
    if org_id != EMPIRE_DIGITAL_COMPANY_ID:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Social ingest is only allowed for the Empire Digital organization",
        )
    try:
        return await social_ingest_service.ingest_social_lead(
            db,
            body,
            organization_id=org_id,
            actor_user_id=int(actor["id"]) if actor.get("id") else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
