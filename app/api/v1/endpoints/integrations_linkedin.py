import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.logs.audit import record_action
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
    except (RuntimeError, ValueError, TypeError, TimeoutError, ConnectionError, OSError) as exc:
        logger.warning("request failed: %s", exc)
        raise HTTPException(status_code=400, detail="Connection failed. Check credentials and try again.") from exc
    await record_action(
        db, event_type="integration_connected", actor_user_id=actor["id"],
        organization_id=actor["org_id"], entity_type="integration",
        entity_id=info["id"], payload_json={"type": "linkedin", "status": "ok"},
    )
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
        logger.warning("request failed: %s", exc)
        raise HTTPException(status_code=400, detail="Connection failed. Check credentials and try again.") from exc
    await record_action(
        db, event_type="linkedin_post_published", actor_user_id=actor["id"],
        organization_id=actor["org_id"], entity_type="integration",
        entity_id=None, payload_json={"post_id": result["post_id"]},
    )
    return LinkedInPublishResult(**result)
