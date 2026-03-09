from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles, require_sensitive_financial_roles
from app.logs.audit import record_action
from pydantic import BaseModel, Field

from app.schemas.contact import (
    ContactCreate,
    ContactRead,
    ContactUpdate,
    LeadQualificationUpdate,
    LeadRouteRequest,
    LeadRouteResponse,
    PipelineSummary,
)
from app.services import contact as contact_service


class MergeRequest(BaseModel):
    primary_id: int = Field(..., ge=1)
    duplicate_ids: list[int] = Field(..., min_length=1)

router = APIRouter(prefix="/contacts", tags=["Contacts"])


def _mask_contact_for_role(contact: ContactRead, role: object) -> ContactRead:
    from app.core.data_classification import sanitize_dict_for_role
    role_str = str(role or "STAFF")
    raw = contact.model_dump()
    sanitized = sanitize_dict_for_role(raw, "contacts", role_str)
    return ContactRead.model_validate(sanitized)


def _mask_contacts_for_role(contacts: list[ContactRead], role: object) -> list[ContactRead]:
    return [_mask_contact_for_role(c, role) for c in contacts]


@router.post("", response_model=ContactRead, status_code=201)
async def create_contact(
    data: ContactCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF")),
) -> ContactRead:
    """Add a person to your network."""
    contact = await contact_service.create_contact(db, data, organization_id=actor["org_id"])
    await record_action(
        db,
        event_type="contact_created",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="contact",
        entity_id=contact.id,
        payload_json={"name": data.name},
    )
    # Fire-and-forget enrichment
    import asyncio
    from app.services.contact_enrichment import enrich_contact_background
    try:
        asyncio.get_running_loop().create_task(
            enrich_contact_background(contact.id, int(actor["org_id"]))
        )
    except RuntimeError:
        pass
    return _mask_contact_for_role(ContactRead.model_validate(contact, from_attributes=True), actor.get("role"))


@router.get("/pipeline-summary", response_model=list[PipelineSummary])
async def pipeline_summary(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_sensitive_financial_roles()),
) -> list[PipelineSummary]:
    """Aggregate count + deal value per pipeline stage."""
    return await contact_service.get_pipeline_summary(
        db,
        organization_id=actor["org_id"],
        actor_org_id=actor["org_id"],
        actor_role=str(actor.get("role", "")),
    )


@router.get("/follow-up-due", response_model=list[ContactRead])
async def follow_up_due(
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF")),
) -> list[ContactRead]:
    """Contacts whose next_follow_up_at is in the past or today."""
    contacts = await contact_service.get_follow_up_due(
        db,
        organization_id=actor["org_id"],
        limit=limit,
        actor_org_id=actor["org_id"],
        actor_role=str(actor.get("role", "")),
    )
    payload = [ContactRead.model_validate(c, from_attributes=True) for c in contacts]
    return _mask_contacts_for_role(payload, actor.get("role"))


@router.get("", response_model=list[ContactRead])
async def list_contacts(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0, le=10_000),
    pipeline_stage: str | None = Query(None),
    lead_score_min: int | None = Query(None, ge=0, le=100),
    lead_score_max: int | None = Query(None, ge=0, le=100),
    relationship: str | None = Query(None),
    search: str | None = Query(None, max_length=200),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF")),
) -> list[ContactRead]:
    """List contacts with optional CRM filters."""
    contacts = await contact_service.list_contacts(
        db,
        organization_id=actor["org_id"],
        actor_org_id=actor["org_id"],
        actor_role=str(actor.get("role", "")),
        limit=limit,
        offset=offset,
        pipeline_stage=pipeline_stage,
        lead_score_min=lead_score_min,
        lead_score_max=lead_score_max,
        relationship=relationship,
        search=search,
    )
    payload = [ContactRead.model_validate(c, from_attributes=True) for c in contacts]
    return _mask_contacts_for_role(payload, actor.get("role"))


# ── Contact Intelligence (must be before /{contact_id} parametric routes) ───


@router.get("/intelligence")
async def contact_intelligence(
    stale_days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    """Contact intelligence: pipeline analytics, stale contacts, follow-up suggestions."""
    from app.services.contact_intelligence import get_contact_intelligence_summary

    return await get_contact_intelligence_summary(
        db, organization_id=int(actor["org_id"]), stale_days=stale_days,
    )


@router.post("/enrich")
async def batch_enrich_contacts(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    """Batch-enrich contacts: auto-fill company, lead score from email domain."""
    from app.services.contact_enrichment import batch_enrich
    return await batch_enrich(db, organization_id=int(actor["org_id"]))


@router.post("/intelligence/rescore")
async def rescore_contacts(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    """Re-score all contacts based on current attributes and activity."""
    from app.services.contact_intelligence import batch_score_contacts

    result = await batch_score_contacts(db, organization_id=int(actor["org_id"]))
    await record_action(
        db,
        event_type="contacts_rescored",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="contact",
        entity_id=None,
        payload_json=result,
    )
    return result


@router.get("/duplicates")
async def find_duplicates(
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> list[dict]:
    """Find potential duplicate contacts by matching email or phone."""
    return await contact_service.find_duplicates(db, organization_id=actor["org_id"], limit=limit)


@router.post("/merge", response_model=ContactRead)
async def merge_contacts(
    data: MergeRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> ContactRead:
    """Merge duplicate contacts into a primary contact."""
    result = await contact_service.merge_contacts(
        db, organization_id=actor["org_id"],
        primary_id=data.primary_id, duplicate_ids=data.duplicate_ids,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Primary contact not found")
    await record_action(
        db, event_type="contacts_merged", actor_user_id=actor["id"],
        organization_id=actor["org_id"], entity_type="contact", entity_id=data.primary_id,
        payload_json={"primary_id": data.primary_id, "merged_ids": data.duplicate_ids},
    )
    return ContactRead.model_validate(result, from_attributes=True)


@router.get("/pipeline-analytics")
async def pipeline_analytics(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_sensitive_financial_roles()),
) -> dict:
    """Pipeline funnel analytics with conversion rates and win rate."""
    return await contact_service.get_pipeline_analytics(db, organization_id=actor["org_id"])


@router.get("/{contact_id}/timeline")
async def contact_timeline(
    contact_id: int,
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF")),
) -> list[dict]:
    """Unified activity timeline for a contact — events, deals, notes."""
    from app.services.contact_timeline import get_contact_timeline

    contact = await contact_service.get_contact(
        db, contact_id, organization_id=actor["org_id"],
        actor_org_id=actor["org_id"], actor_role=str(actor.get("role", "")),
    )
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    return await get_contact_timeline(db, contact_id=contact_id, organization_id=actor["org_id"], limit=limit)


@router.get("/{contact_id}", response_model=ContactRead)
async def get_contact(
    contact_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF")),
) -> ContactRead:
    contact = await contact_service.get_contact(
        db,
        contact_id,
        organization_id=actor["org_id"],
        actor_org_id=actor["org_id"],
        actor_role=str(actor.get("role", "")),
    )
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    payload = ContactRead.model_validate(contact, from_attributes=True)
    return _mask_contact_for_role(payload, actor.get("role"))


@router.patch("/{contact_id}", response_model=ContactRead)
async def update_contact(
    contact_id: int,
    data: ContactUpdate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> ContactRead:
    contact = await contact_service.update_contact(db, contact_id, data, organization_id=actor["org_id"])
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    await record_action(
        db, event_type="contact_updated", actor_user_id=actor["id"],
        organization_id=actor["org_id"], entity_type="contact", entity_id=contact_id,
        payload_json=data.model_dump(exclude_unset=True, mode="json"),
    )
    return _mask_contact_for_role(ContactRead.model_validate(contact, from_attributes=True), actor.get("role"))


@router.delete("/{contact_id}", status_code=204)
async def delete_contact(
    contact_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> None:
    deleted = await contact_service.delete_contact(db, contact_id, organization_id=actor["org_id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Contact not found")
    await record_action(
        db, event_type="contact_deleted", actor_user_id=actor["id"],
        organization_id=actor["org_id"], entity_type="contact", entity_id=contact_id,
        payload_json={"contact_id": contact_id},
    )


@router.post("/{contact_id}/route", response_model=LeadRouteResponse)
async def route_contact(
    contact_id: int,
    data: LeadRouteRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> LeadRouteResponse:
    try:
        routed = await contact_service.route_contact(
            db,
            contact_id=contact_id,
            organization_id=actor["org_id"],
            actor_user_id=actor["id"],
            actor_org_id=actor["org_id"],
            actor_role=str(actor.get("role", "")),
            lead_type=data.lead_type,
            routed_company_id=data.routed_company_id,
            routing_reason=data.routing_reason,
        )
    except ValueError as exc:
        if str(exc) == "invalid_routing_transition":
            raise HTTPException(status_code=409, detail="Invalid routing status transition") from exc
        raise
    if routed is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    await record_action(
        db,
        event_type="contact_routed",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="contact",
        entity_id=contact_id,
        payload_json={
            "lead_type": routed.lead_type,
            "routing_status": routed.routing_status,
            "routed_company_id": routed.routed_company_id,
            "routing_source": routed.routing_source,
            "routing_rule_id": routed.routing_rule_id,
        },
    )
    return LeadRouteResponse(
        contact_id=routed.id,
        lead_owner_company_id=routed.lead_owner_company_id,
        routed_company_id=routed.routed_company_id,
        lead_type=routed.lead_type,
        routing_status=routed.routing_status,
        routing_reason=routed.routing_reason,
        routing_source=routed.routing_source,
        routing_rule_id=routed.routing_rule_id,
        routed_at=routed.routed_at,
        routed_by_user_id=routed.routed_by_user_id,
    )


@router.post("/{contact_id}/qualify", response_model=ContactRead)
async def qualify_contact(
    contact_id: int,
    data: LeadQualificationUpdate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> ContactRead:
    try:
        qualified = await contact_service.qualify_contact(
            db,
            contact_id=contact_id,
            organization_id=actor["org_id"],
            actor_org_id=actor["org_id"],
            actor_role=str(actor.get("role", "")),
            lead_type=data.lead_type,
            qualified_score=data.qualified_score,
            qualified_status=data.qualified_status,
            qualification_notes=data.qualification_notes,
            routing_status=data.routing_status,
        )
    except ValueError as exc:
        if str(exc) == "invalid_routing_transition":
            raise HTTPException(status_code=409, detail="Invalid routing status transition") from exc
        raise
    if qualified is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    await record_action(
        db,
        event_type="contact_qualified",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="contact",
        entity_id=contact_id,
        payload_json={
            "qualified_score": qualified.qualified_score,
            "qualified_status": qualified.qualified_status,
            "routing_status": qualified.routing_status,
        },
    )
    return _mask_contact_for_role(ContactRead.model_validate(qualified, from_attributes=True), actor.get("role"))
