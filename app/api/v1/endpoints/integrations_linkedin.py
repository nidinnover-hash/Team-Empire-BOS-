import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints._integration_helpers import (
    CONNECT_EXCEPTIONS,
    audit_connect_success,
    audit_sync,
    handle_connect_error,
)
from app.core.deps import get_db
from app.core.rbac import require_roles
from app.schemas.integration import (
    LinkedInConnectRequest,
    LinkedInPublishRequest,
    LinkedInPublishResult,
    LinkedInStatusRead,
)
from app.services import linkedin_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Integrations"])


@router.post("/linkedin/connect", response_model=LinkedInStatusRead, status_code=201)
async def linkedin_connect(
    data: LinkedInConnectRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> LinkedInStatusRead:
    try:
        info = await linkedin_service.connect_linkedin(
            db, org_id=int(actor["org_id"]), access_token=data.access_token,
        )
    except CONNECT_EXCEPTIONS as exc:
        await handle_connect_error(db, integration_type="linkedin", actor=actor, exc=exc)
    await audit_connect_success(db, integration_type="linkedin", actor=actor, entity_id=info["id"])
    return LinkedInStatusRead(connected=True, name=info.get("name"), author_urn=info.get("author_urn"))


@router.get("/linkedin/status", response_model=LinkedInStatusRead)
async def linkedin_status(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> LinkedInStatusRead:
    status = await linkedin_service.get_linkedin_status(db, org_id=int(actor["org_id"]))
    return LinkedInStatusRead(**status)


@router.post("/linkedin/publish", response_model=LinkedInPublishResult)
async def linkedin_publish(
    data: LinkedInPublishRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> LinkedInPublishResult:
    try:
        result = await linkedin_service.publish_post(
            db, org_id=int(actor["org_id"]), text=data.text, visibility=data.visibility,
        )
    except ValueError as exc:
        logger.warning("linkedin publish failed: %s", exc)
        raise HTTPException(status_code=400, detail="Publish failed. Check connection and try again.") from exc
    await audit_sync(
        db, event_type="linkedin_post_published", actor=actor,
        payload={"post_id": result["post_id"]},
    )
    return LinkedInPublishResult(**result)
