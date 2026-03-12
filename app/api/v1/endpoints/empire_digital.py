import csv
import io
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.lead_routing import EMPIRE_DIGITAL_COMPANY_ID
from app.core.rbac import require_roles
from app.logs.audit import record_action
from app.schemas.contact import ContactRead
from app.schemas.empire_digital import (
    BulkLeadActionResult,
    BulkLeadQualifyRequest,
    BulkLeadRouteRequest,
    EmpireSlaConfigRead,
    EmpireSlaConfigUpdate,
    EscalateStaleLeadsRequest,
    EscalateStaleLeadsResult,
    ScorecardRead,
)
from app.schemas.lead_routing_rule import (
    LeadRoutingRuleCreate,
    LeadRoutingRuleRead,
    LeadRoutingRuleUpdate,
)
from app.schemas.marketing_intelligence import (
    EmpireDigitalCockpitRead,
    FounderFlowReportRead,
    MarketingIntelligenceCreate,
    MarketingIntelligenceRead,
    MarketingIntelligenceReview,
    MarketingIntelligenceReviewResult,
)
from app.services import contact as contact_service
from app.services import empire_digital as empire_digital_service
from app.services import lead_routing_policy as lead_routing_policy_service

router = APIRouter(prefix="/empire-digital", tags=["Empire Digital"])


@router.get("/cockpit", response_model=EmpireDigitalCockpitRead)
async def get_cockpit(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> EmpireDigitalCockpitRead:
    return await empire_digital_service.build_empire_cockpit(
        db,
        actor_org_id=int(actor["org_id"]),
        actor_role=str(actor.get("role", "")).upper(),
    )


@router.get("/scorecard", response_model=ScorecardRead)
async def get_scorecard(
    window_days: int = Query(7, ge=1, le=31),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> ScorecardRead:
    """Scorecard tiles with green/amber/red bands (Q1 targets). Empire Digital org only."""
    if int(actor["org_id"]) != EMPIRE_DIGITAL_COMPANY_ID:
        raise HTTPException(status_code=403, detail="Scorecard available for Empire Digital only")
    return await empire_digital_service.get_scorecard_empire_digital(
        db,
        actor_org_id=int(actor["org_id"]),
        actor_role=str(actor.get("role", "")).upper(),
        window_days=window_days,
    )


@router.get("/leads", response_model=list[ContactRead])
async def list_lead_queue(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0, le=10_000),
    lead_type: str | None = Query(None),
    routing_status: str | None = Query(None),
    search: str | None = Query(None, max_length=200),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list[ContactRead]:
    rows = await contact_service.list_contacts(
        db,
        organization_id=int(actor["org_id"]),
        actor_org_id=int(actor["org_id"]),
        actor_role=str(actor.get("role", "")).upper(),
        limit=limit,
        offset=offset,
        search=search,
    )
    if lead_type:
        rows = [r for r in rows if str(r.lead_type or "") == str(lead_type)]
    if routing_status:
        rows = [r for r in rows if str(r.routing_status or "") == str(routing_status)]
    return [ContactRead.model_validate(row, from_attributes=True) for row in rows]


@router.get("/leads/export")
async def export_leads(
    format: str = Query("json"),
    limit: int = Query(500, ge=1, le=5000),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    sla_cfg = await empire_digital_service.get_empire_sla_config(
        db, organization_id=int(actor["org_id"])
    )
    stale_days = int(sla_cfg.stale_unrouted_days)
    now = datetime.now(UTC)

    def _as_utc(dt):
        if dt is None:
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)

    def _age_bucket(days_open: int) -> str:
        if days_open <= 1:
            return "0_1d"
        if days_open <= 3:
            return "2_3d"
        if days_open <= 7:
            return "4_7d"
        return "8d_plus"

    rows = await empire_digital_service.list_scoped_leads(
        db,
        actor_org_id=int(actor["org_id"]),
        actor_role=str(actor.get("role", "")).upper(),
        limit=limit,
        offset=0,
    )
    payload = [
        {
            "id": row.id,
            "name": row.name,
            "lead_type": row.lead_type,
            "routing_status": row.routing_status,
            "routing_source": row.routing_source,
            "routing_rule_id": row.routing_rule_id,
            "routing_reason": row.routing_reason,
            "routed_company_id": row.routed_company_id,
            "qualified_status": row.qualified_status,
            "qualified_score": row.qualified_score,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "routed_at": row.routed_at.isoformat() if row.routed_at else None,
            "days_open": (
                (now - _as_utc(row.created_at)).days
                if _as_utc(row.created_at) is not None
                else None
            ),
            "aging_bucket": (
                _age_bucket((now - _as_utc(row.created_at)).days)
                if _as_utc(row.created_at) is not None
                else None
            ),
            "stale_by_sla": bool(
                _as_utc(row.created_at)
                and row.routed_company_id is None
                and (now - _as_utc(row.created_at)).days >= stale_days
            ),
        }
        for row in rows
    ]
    if str(format).lower() == "csv":
        output = io.StringIO()
        fieldnames = [
            "id", "name", "lead_type", "routing_status", "routing_source",
            "routing_rule_id", "routing_reason", "routed_company_id",
            "qualified_status", "qualified_score", "created_at", "routed_at",
            "days_open", "aging_bucket", "stale_by_sla",
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for row in payload:
            writer.writerow(row)
        return PlainTextResponse(
            content=output.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="empire-leads.csv"'},
        )
    return JSONResponse(content={"items": payload, "count": len(payload)})


@router.get("/leads/{contact_id}", response_model=ContactRead)
async def get_lead_detail(
    contact_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> ContactRead:
    row = await contact_service.get_contact(
        db,
        contact_id,
        organization_id=int(actor["org_id"]),
        actor_org_id=int(actor["org_id"]),
        actor_role=str(actor.get("role", "")).upper(),
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    return ContactRead.model_validate(row, from_attributes=True)


@router.post("/leads/bulk-route", response_model=BulkLeadActionResult)
async def bulk_route_leads(
    data: BulkLeadRouteRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> BulkLeadActionResult:
    actor_org_id = int(actor["org_id"])
    actor_role = str(actor.get("role", "")).upper()
    updated_ids: list[int] = []
    skipped = 0
    for contact_id in data.contact_ids:
        try:
            row = await contact_service.route_contact(
                db,
                contact_id=int(contact_id),
                organization_id=actor_org_id,
                actor_user_id=int(actor["id"]),
                actor_org_id=actor_org_id,
                actor_role=actor_role,
                lead_type=data.lead_type,
                routed_company_id=data.routed_company_id,
                routing_reason=data.routing_reason,
            )
        except ValueError:
            skipped += 1
            continue
        if row is None:
            skipped += 1
            continue
        updated_ids.append(int(row.id))
    await record_action(
        db,
        event_type="bulk_contact_routed",
        actor_user_id=int(actor["id"]),
        organization_id=actor_org_id,
        entity_type="contact",
        entity_id=None,
        payload_json={"requested": len(data.contact_ids), "updated": len(updated_ids)},
    )
    return BulkLeadActionResult(
        requested=len(data.contact_ids),
        updated=len(updated_ids),
        skipped=skipped,
        updated_contact_ids=updated_ids,
    )


@router.post("/leads/bulk-qualify", response_model=BulkLeadActionResult)
async def bulk_qualify_leads(
    data: BulkLeadQualifyRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> BulkLeadActionResult:
    actor_org_id = int(actor["org_id"])
    actor_role = str(actor.get("role", "")).upper()
    updated_ids: list[int] = []
    skipped = 0
    for contact_id in data.contact_ids:
        try:
            row = await contact_service.qualify_contact(
                db,
                contact_id=int(contact_id),
                organization_id=actor_org_id,
                actor_org_id=actor_org_id,
                actor_role=actor_role,
                lead_type=data.lead_type,
                qualified_score=data.qualified_score,
                qualified_status=data.qualified_status,
                qualification_notes=data.qualification_notes,
                routing_status=data.routing_status,
            )
        except ValueError:
            skipped += 1
            continue
        if row is None:
            skipped += 1
            continue
        updated_ids.append(int(row.id))
    await record_action(
        db,
        event_type="bulk_contact_qualified",
        actor_user_id=int(actor["id"]),
        organization_id=actor_org_id,
        entity_type="contact",
        entity_id=None,
        payload_json={"requested": len(data.contact_ids), "updated": len(updated_ids)},
    )
    return BulkLeadActionResult(
        requested=len(data.contact_ids),
        updated=len(updated_ids),
        skipped=skipped,
        updated_contact_ids=updated_ids,
    )


@router.post("/leads/escalate-stale", response_model=EscalateStaleLeadsResult)
async def escalate_stale_leads(
    data: EscalateStaleLeadsRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> EscalateStaleLeadsResult:
    decision_card_ids = await empire_digital_service.escalate_stale_leads(
        db,
        actor_org_id=int(actor["org_id"]),
        actor_role=str(actor.get("role", "")).upper(),
        actor_user_id=int(actor["id"]),
        contact_ids=data.contact_ids,
        limit=int(data.limit),
    )
    await record_action(
        db,
        event_type="stale_leads_escalated",
        actor_user_id=int(actor["id"]),
        organization_id=int(actor["org_id"]),
        entity_type="decision_card",
        entity_id=None,
        payload_json={"escalated": len(decision_card_ids)},
    )
    considered = len(data.contact_ids) if data.contact_ids else int(data.limit)
    return EscalateStaleLeadsResult(
        considered=considered,
        escalated=len(decision_card_ids),
        decision_card_ids=decision_card_ids,
    )


@router.get("/sla-policy", response_model=EmpireSlaConfigRead)
async def get_empire_sla_policy(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> EmpireSlaConfigRead:
    return await empire_digital_service.get_empire_sla_config(
        db, organization_id=int(actor["org_id"])
    )


@router.patch("/sla-policy", response_model=EmpireSlaConfigRead)
async def update_empire_sla_policy(
    data: EmpireSlaConfigUpdate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> EmpireSlaConfigRead:
    return await empire_digital_service.update_empire_sla_config(
        db,
        organization_id=int(actor["org_id"]),
        stale_unrouted_days=int(data.stale_unrouted_days),
        warning_stale_count=int(data.warning_stale_count),
        warning_unrouted_count=int(data.warning_unrouted_count),
    )


@router.get("/founder-report", response_model=FounderFlowReportRead)
async def get_founder_report(
    window_days: int = Query(7, ge=1, le=31),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> FounderFlowReportRead:
    return await empire_digital_service.build_founder_flow_report(
        db,
        actor_org_id=int(actor["org_id"]),
        actor_role=str(actor.get("role", "")).upper(),
        window_days=window_days,
    )


@router.get("/routing-rules", response_model=list[LeadRoutingRuleRead])
async def list_routing_rules(
    active_only: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list[LeadRoutingRuleRead]:
    if int(actor["org_id"]) != EMPIRE_DIGITAL_COMPANY_ID:
        raise HTTPException(status_code=403, detail="Only Empire Digital can view routing rules")
    rules = await lead_routing_policy_service.list_rules(
        db,
        owner_company_id=EMPIRE_DIGITAL_COMPANY_ID,
        active_only=active_only,
    )
    return [LeadRoutingRuleRead.model_validate(rule, from_attributes=True) for rule in rules]


@router.post("/routing-rules", response_model=LeadRoutingRuleRead, status_code=201)
async def create_routing_rule(
    data: LeadRoutingRuleCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> LeadRoutingRuleRead:
    if int(actor["org_id"]) != EMPIRE_DIGITAL_COMPANY_ID:
        raise HTTPException(status_code=403, detail="Only Empire Digital can manage routing rules")
    try:
        rule = await lead_routing_policy_service.create_rule(
            db,
            owner_company_id=EMPIRE_DIGITAL_COMPANY_ID,
            actor_user_id=int(actor["id"]),
            data=data,
        )
    except ValueError as exc:
        msg = str(exc)
        if msg == "target_company_not_found":
            raise HTTPException(status_code=422, detail="Target company does not exist") from exc
        if msg == "duplicate_priority_for_lead_type":
            raise HTTPException(status_code=409, detail="Duplicate priority for this lead type") from exc
        raise
    await record_action(
        db,
        event_type="lead_routing_rule_created",
        actor_user_id=int(actor["id"]),
        organization_id=int(actor["org_id"]),
        entity_type="lead_routing_rule",
        entity_id=rule.id,
        payload_json={"lead_type": rule.lead_type, "target_company_id": rule.target_company_id},
    )
    return LeadRoutingRuleRead.model_validate(rule, from_attributes=True)


@router.patch("/routing-rules/{rule_id}", response_model=LeadRoutingRuleRead)
async def update_routing_rule(
    rule_id: int,
    data: LeadRoutingRuleUpdate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> LeadRoutingRuleRead:
    if int(actor["org_id"]) != EMPIRE_DIGITAL_COMPANY_ID:
        raise HTTPException(status_code=403, detail="Only Empire Digital can manage routing rules")
    try:
        rule = await lead_routing_policy_service.update_rule(
            db,
            owner_company_id=EMPIRE_DIGITAL_COMPANY_ID,
            actor_user_id=int(actor["id"]),
            rule_id=rule_id,
            data=data,
        )
    except ValueError as exc:
        msg = str(exc)
        if msg == "target_company_not_found":
            raise HTTPException(status_code=422, detail="Target company does not exist") from exc
        if msg == "duplicate_priority_for_lead_type":
            raise HTTPException(status_code=409, detail="Duplicate priority for this lead type") from exc
        raise
    if rule is None:
        raise HTTPException(status_code=404, detail="Routing rule not found")
    await record_action(
        db,
        event_type="lead_routing_rule_updated",
        actor_user_id=int(actor["id"]),
        organization_id=int(actor["org_id"]),
        entity_type="lead_routing_rule",
        entity_id=rule.id,
        payload_json={"is_active": rule.is_active, "target_company_id": rule.target_company_id},
    )
    return LeadRoutingRuleRead.model_validate(rule, from_attributes=True)


@router.post("/intelligence", response_model=MarketingIntelligenceRead, status_code=201)
async def submit_intelligence(
    data: MarketingIntelligenceCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF")),
) -> MarketingIntelligenceRead:
    item = await empire_digital_service.submit_marketing_intelligence(
        db,
        actor_org_id=int(actor["org_id"]),
        actor_user_id=int(actor["id"]),
        data=data,
    )
    await record_action(
        db,
        event_type="marketing_intelligence_submitted",
        actor_user_id=int(actor["id"]),
        organization_id=int(actor["org_id"]),
        entity_type="marketing_intelligence",
        entity_id=item.id,
        payload_json={"category": item.category, "priority": item.priority},
    )
    return empire_digital_service.to_marketing_intelligence_read(item)


@router.get("/intelligence", response_model=list[MarketingIntelligenceRead])
async def list_intelligence(
    status: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0, le=10_000),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF")),
) -> list[MarketingIntelligenceRead]:
    rows = await empire_digital_service.list_marketing_intelligence(
        db,
        actor_org_id=int(actor["org_id"]),
        actor_role=str(actor.get("role", "")).upper(),
        status=status,
        limit=limit,
        offset=offset,
    )
    return [empire_digital_service.to_marketing_intelligence_read(row) for row in rows]


@router.post("/intelligence/{item_id}/review", response_model=MarketingIntelligenceReviewResult)
async def review_intelligence(
    item_id: int,
    data: MarketingIntelligenceReview,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> MarketingIntelligenceReviewResult:
    role = str(actor.get("role", "")).upper()
    org_id = int(actor["org_id"])
    if org_id != EMPIRE_DIGITAL_COMPANY_ID:
        raise HTTPException(status_code=403, detail="Only Empire Digital can review marketing intelligence")
    updated = await empire_digital_service.review_marketing_intelligence(
        db,
        item_id=item_id,
        actor_org_id=org_id,
        actor_role=role,
        actor_user_id=int(actor["id"]),
        status=data.status,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Marketing intelligence not found")
    decision_card_id: int | None = None
    if data.create_decision_card:
        decision_card_id = await empire_digital_service.create_decision_card_for_intelligence(
            db,
            org_id=org_id,
            actor_user_id=int(actor["id"]),
            item=updated,
            workspace_id=data.workspace_id,
        )
    await record_action(
        db,
        event_type="marketing_intelligence_reviewed",
        actor_user_id=int(actor["id"]),
        organization_id=org_id,
        entity_type="marketing_intelligence",
        entity_id=updated.id,
        payload_json={"status": updated.status, "decision_card_id": decision_card_id},
    )
    return MarketingIntelligenceReviewResult(
        item=empire_digital_service.to_marketing_intelligence_read(updated),
        decision_card_id=decision_card_id,
    )
