from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.lead_routing import EMPIRE_DIGITAL_COMPANY_ID, apply_contact_visibility_scope
from app.models.contact import Contact
from app.models.decision_card import DecisionCard
from app.models.marketing_intelligence import MarketingIntelligence
from app.models.organization import Organization
from app.schemas.decision_card import DecisionCardCreate, DecisionOption
from app.schemas.empire_digital import EmpireSlaConfigRead
from app.schemas.marketing_intelligence import (
    CockpitCount,
    EmpireDigitalCockpitRead,
    FounderFlowReportRead,
    FounderReportDailyPoint,
    MarketingIntelligenceCreate,
    MarketingIntelligenceRead,
)
from app.services import decision_card as decision_card_service
from app.services import organization as organization_service
from app.services import workspace as workspace_service

INTELLIGENCE_STATUSES = {"submitted", "reviewing", "accepted", "rejected", "applied"}


def _normalize_intelligence_status(value: object) -> str:
    status = str(value or "submitted").strip().lower()
    return status if status in INTELLIGENCE_STATUSES else "submitted"


def _is_empire_admin_scope(*, actor_org_id: int, actor_role: str) -> bool:
    return actor_org_id == EMPIRE_DIGITAL_COMPANY_ID and actor_role in {"CEO", "ADMIN", "MANAGER"}


def _visibility_scope_label(*, actor_org_id: int, actor_role: str) -> str:
    if actor_org_id == EMPIRE_DIGITAL_COMPANY_ID and actor_role == "CEO":
        return "cross_company"
    if actor_org_id == EMPIRE_DIGITAL_COMPANY_ID:
        return "empire"
    return "company_scoped"


def _normalize_dt(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


async def get_empire_sla_config(db: AsyncSession, *, organization_id: int) -> EmpireSlaConfigRead:
    config = await organization_service.get_policy_config(db, organization_id)
    raw = config.get("empire_digital", {}).get("sla", {}) if isinstance(config, dict) else {}
    return EmpireSlaConfigRead(
        stale_unrouted_days=int(raw.get("stale_unrouted_days", 3)),
        warning_stale_count=int(raw.get("warning_stale_count", 3)),
        warning_unrouted_count=int(raw.get("warning_unrouted_count", 8)),
    )


async def update_empire_sla_config(
    db: AsyncSession,
    *,
    organization_id: int,
    stale_unrouted_days: int,
    warning_stale_count: int,
    warning_unrouted_count: int,
) -> EmpireSlaConfigRead:
    current = await organization_service.get_policy_config(db, organization_id)
    empire_cfg = dict(current.get("empire_digital", {})) if isinstance(current, dict) else {}
    empire_cfg["sla"] = {
        "stale_unrouted_days": int(stale_unrouted_days),
        "warning_stale_count": int(warning_stale_count),
        "warning_unrouted_count": int(warning_unrouted_count),
    }
    await organization_service.update_policy_config(
        db,
        organization_id=organization_id,
        config={"empire_digital": empire_cfg},
    )
    return await get_empire_sla_config(db, organization_id=organization_id)


async def submit_marketing_intelligence(
    db: AsyncSession,
    *,
    actor_org_id: int,
    actor_user_id: int,
    data: MarketingIntelligenceCreate,
) -> MarketingIntelligence:
    record = MarketingIntelligence(
        owner_company_id=EMPIRE_DIGITAL_COMPANY_ID,
        source_company_id=actor_org_id,
        category=data.category,
        title=data.title,
        summary=data.summary,
        confidence=data.confidence,
        priority=data.priority,
        suggested_action=data.suggested_action,
        status="submitted",
        created_by_user_id=actor_user_id,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


async def list_marketing_intelligence(
    db: AsyncSession,
    *,
    actor_org_id: int,
    actor_role: str,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[MarketingIntelligence]:
    query = select(MarketingIntelligence).order_by(
        MarketingIntelligence.created_at.desc()
    )
    if _is_empire_admin_scope(actor_org_id=actor_org_id, actor_role=actor_role):
        query = query.where(
            MarketingIntelligence.owner_company_id == EMPIRE_DIGITAL_COMPANY_ID
        )
    else:
        query = query.where(
            MarketingIntelligence.source_company_id == actor_org_id
        )
    if status:
        query = query.where(
            MarketingIntelligence.status == _normalize_intelligence_status(status)
        )
    result = await db.execute(query.offset(offset).limit(limit))
    return list(result.scalars().all())


async def review_marketing_intelligence(
    db: AsyncSession,
    *,
    item_id: int,
    actor_org_id: int,
    actor_role: str,
    actor_user_id: int,
    status: str,
) -> MarketingIntelligence | None:
    if not _is_empire_admin_scope(actor_org_id=actor_org_id, actor_role=actor_role):
        return None
    result = await db.execute(
        select(MarketingIntelligence).where(
            MarketingIntelligence.id == item_id,
            MarketingIntelligence.owner_company_id == EMPIRE_DIGITAL_COMPANY_ID,
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        return None
    item.status = _normalize_intelligence_status(status)
    item.reviewed_by_user_id = actor_user_id
    item.reviewed_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(item)
    return item


async def build_empire_cockpit(
    db: AsyncSession,
    *,
    actor_org_id: int,
    actor_role: str,
) -> EmpireDigitalCockpitRead:
    sla_cfg = await get_empire_sla_config(db, organization_id=actor_org_id)
    stale_days = int(sla_cfg.stale_unrouted_days)
    query = apply_contact_visibility_scope(
        select(Contact),
        actor_org_id=actor_org_id,
        actor_role=actor_role,
    )
    result = await db.execute(query)
    contacts = list(result.scalars().all())

    lead_type_counts: Counter[str] = Counter()
    routed_company_counts: Counter[str] = Counter()
    qualification_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()

    total = len(contacts)
    now = datetime.now(UTC)
    stale_cutoff = now - timedelta(days=stale_days)
    new_leads = 0
    unrouted_leads = 0
    routed_leads = 0
    stale_unrouted = 0
    aging_buckets: Counter[str] = Counter()
    total_routing_hours = 0.0
    routed_with_timestamp = 0

    for contact in contacts:
        lead_type_counts[str(contact.lead_type or "general")] += 1
        routed_company_key = (
            str(contact.routed_company_id)
            if contact.routed_company_id is not None
            else "unrouted"
        )
        routed_company_counts[routed_company_key] += 1
        qualification_counts[str(contact.qualified_status or "unqualified")] += 1
        source_counts[str(contact.source_channel or "unknown")] += 1
        if contact.pipeline_stage == "new":
            new_leads += 1
        if contact.routed_company_id is None:
            unrouted_leads += 1
            created_at = getattr(contact, "created_at", None)
            if created_at is not None:
                created_at = _normalize_dt(created_at)
                if created_at is None:
                    continue
                age_days = (now - created_at).days
                if age_days <= 1:
                    aging_buckets["0_1d"] += 1
                elif age_days <= 3:
                    aging_buckets["2_3d"] += 1
                elif age_days <= 7:
                    aging_buckets["4_7d"] += 1
                else:
                    aging_buckets["8d_plus"] += 1
                if created_at <= stale_cutoff:
                    stale_unrouted += 1
        else:
            routed_leads += 1
            created_at = getattr(contact, "created_at", None)
            routed_at = getattr(contact, "routed_at", None)
            created_at = _normalize_dt(created_at)
            routed_at = _normalize_dt(routed_at)
            if created_at is not None and routed_at is not None and routed_at >= created_at:
                total_routing_hours += (routed_at - created_at).total_seconds() / 3600.0
                routed_with_timestamp += 1

    intelligence_query = select(MarketingIntelligence)
    if _is_empire_admin_scope(actor_org_id=actor_org_id, actor_role=actor_role):
        intelligence_query = intelligence_query.where(
            MarketingIntelligence.owner_company_id == EMPIRE_DIGITAL_COMPANY_ID
        )
    else:
        intelligence_query = intelligence_query.where(
            MarketingIntelligence.source_company_id == actor_org_id
        )
    intelligence_result = await db.execute(intelligence_query)
    intelligence_items = list(intelligence_result.scalars().all())
    pending_intelligence = sum(1 for item in intelligence_items if item.status in {"submitted", "reviewing"})

    routed_ids = sorted(
        {
            int(c.routed_company_id)
            for c in contacts
            if getattr(c, "routed_company_id", None) is not None
        }
    )
    org_name_map: dict[str, str] = {}
    if routed_ids:
        org_rows = await db.execute(
            select(Organization).where(Organization.id.in_(routed_ids))
        )
        org_name_map = {str(org.id): org.name for org in org_rows.scalars().all()}

    def _sorted_counts(counter: Counter[str], *, top: int | None = None) -> list[CockpitCount]:
        items = sorted(counter.items(), key=lambda item: (-item[1], item[0]))
        if top is not None:
            items = items[:top]
        return [
            CockpitCount(
                key=key,
                count=count,
                label=org_name_map.get(key) if key != "unrouted" else "Unrouted",
            )
            for key, count in items
        ]

    return EmpireDigitalCockpitRead(
        total_visible_leads=total,
        new_leads=new_leads,
        unrouted_leads=unrouted_leads,
        routed_leads=routed_leads,
        stale_unrouted_leads=stale_unrouted,
        by_lead_type=_sorted_counts(lead_type_counts),
        by_routed_company=_sorted_counts(routed_company_counts),
        qualification_breakdown=_sorted_counts(qualification_counts),
        top_sources=_sorted_counts(source_counts, top=5),
        unrouted_aging_buckets=_sorted_counts(aging_buckets),
        average_routing_hours=(
            round(total_routing_hours / routed_with_timestamp, 2)
            if routed_with_timestamp > 0
            else None
        ),
        pending_intelligence=pending_intelligence,
        stale_warning_triggered=(
            stale_unrouted >= int(sla_cfg.warning_stale_count)
            or unrouted_leads >= int(sla_cfg.warning_unrouted_count)
        ),
        stale_warning_threshold_count=int(sla_cfg.warning_stale_count),
        warning_unrouted_threshold_count=int(sla_cfg.warning_unrouted_count),
        visibility_scope=_visibility_scope_label(actor_org_id=actor_org_id, actor_role=actor_role),  # type: ignore[arg-type]
    )


async def list_scoped_leads(
    db: AsyncSession,
    *,
    actor_org_id: int,
    actor_role: str,
    limit: int = 100,
    offset: int = 0,
) -> list[Contact]:
    query = apply_contact_visibility_scope(
        select(Contact),
        actor_org_id=actor_org_id,
        actor_role=actor_role,
    )
    result = await db.execute(
        query.order_by(Contact.created_at.desc()).offset(offset).limit(limit)
    )
    return list(result.scalars().all())


def to_marketing_intelligence_read(item: MarketingIntelligence) -> MarketingIntelligenceRead:
    return MarketingIntelligenceRead.model_validate(item, from_attributes=True)


async def create_decision_card_for_intelligence(
    db: AsyncSession,
    *,
    org_id: int,
    actor_user_id: int,
    item: MarketingIntelligence,
    workspace_id: int | None = None,
) -> int:
    if workspace_id is None:
        workspace = await workspace_service.ensure_default_workspace(db, org_id)
        workspace_id = workspace.id
    else:
        workspace = await workspace_service.get_workspace(db, org_id, workspace_id)
        if workspace is None:
            workspace = await workspace_service.ensure_default_workspace(db, org_id)
            workspace_id = workspace.id

    card = await decision_card_service.create_decision_card(
        db,
        org_id=org_id,
        proposed_by=actor_user_id,
        data=DecisionCardCreate(
            workspace_id=workspace_id,
            title=f"Review intelligence: {item.title[:120]}",
            context_summary=item.summary,
            options=[
                DecisionOption(label="Approve campaign adjustment", description="Accept and apply suggested action."),
                DecisionOption(label="Reject for now", description="Keep note, no immediate execution."),
            ],
            recommendation="Approve campaign adjustment",
            category="strategic",
            urgency="normal",
            source_type="marketing_intelligence",
            source_id=str(item.id),
        ),
    )
    return int(card.id)


async def build_founder_flow_report(
    db: AsyncSession,
    *,
    actor_org_id: int,
    actor_role: str,
    window_days: int = 7,
) -> FounderFlowReportRead:
    window_days = max(1, min(31, int(window_days)))
    sla_cfg = await get_empire_sla_config(db, organization_id=actor_org_id)
    stale_days = int(sla_cfg.stale_unrouted_days)
    now = datetime.now(UTC)
    start_day = (now - timedelta(days=window_days - 1)).date()
    days = [start_day + timedelta(days=i) for i in range(window_days)]
    day_keys = [d.isoformat() for d in days]

    contacts_query = apply_contact_visibility_scope(
        select(Contact),
        actor_org_id=actor_org_id,
        actor_role=actor_role,
    ).where(Contact.created_at >= datetime.combine(start_day, datetime.min.time(), tzinfo=UTC))
    contacts_result = await db.execute(contacts_query)
    contacts = list(contacts_result.scalars().all())

    intelligence_query = select(MarketingIntelligence).where(
        MarketingIntelligence.created_at >= datetime.combine(start_day, datetime.min.time(), tzinfo=UTC)
    )
    if _is_empire_admin_scope(actor_org_id=actor_org_id, actor_role=actor_role):
        intelligence_query = intelligence_query.where(
            MarketingIntelligence.owner_company_id == EMPIRE_DIGITAL_COMPANY_ID
        )
    else:
        intelligence_query = intelligence_query.where(
            MarketingIntelligence.source_company_id == actor_org_id
        )
    intelligence_result = await db.execute(intelligence_query)
    intel_items = list(intelligence_result.scalars().all())

    leads_created = defaultdict(int)
    leads_routed = defaultdict(int)
    stale_unrouted = defaultdict(int)
    intel_accepted = defaultdict(int)
    intel_rejected = defaultdict(int)
    escalation_counts = defaultdict(int)

    for contact in contacts:
        created_at = _normalize_dt(getattr(contact, "created_at", None))
        if created_at is None:
            continue
        day = created_at.date().isoformat()
        if day not in day_keys:
            continue
        leads_created[day] += 1
        routed_at = _normalize_dt(getattr(contact, "routed_at", None))
        if routed_at is not None:
            routed_day = routed_at.date().isoformat()
            if routed_day in day_keys:
                leads_routed[routed_day] += 1
        if getattr(contact, "routed_company_id", None) is None and (now - created_at).days >= stale_days:
            stale_unrouted[day] += 1

    for item in intel_items:
        reviewed_at = _normalize_dt(getattr(item, "reviewed_at", None))
        if reviewed_at is None:
            continue
        day = reviewed_at.date().isoformat()
        if day not in day_keys:
            continue
        status = str(getattr(item, "status", "")).lower()
        if status == "accepted":
            intel_accepted[day] += 1
        elif status == "rejected":
            intel_rejected[day] += 1

    escalation_query = select(DecisionCard).where(
        DecisionCard.organization_id == actor_org_id,
        DecisionCard.source_type == "stale_lead_escalation",
        DecisionCard.created_at >= datetime.combine(start_day, datetime.min.time(), tzinfo=UTC),
    )
    escalation_rows = list((await db.execute(escalation_query)).scalars().all())
    for card in escalation_rows:
        created_at = _normalize_dt(getattr(card, "created_at", None))
        if created_at is None:
            continue
        day = created_at.date().isoformat()
        if day in day_keys:
            escalation_counts[day] += 1

    points = [
        FounderReportDailyPoint(
            day=day,
            leads_created=leads_created.get(day, 0),
            leads_routed=leads_routed.get(day, 0),
            stale_unrouted=stale_unrouted.get(day, 0),
            intelligence_accepted=intel_accepted.get(day, 0),
            intelligence_rejected=intel_rejected.get(day, 0),
            escalations_created=escalation_counts.get(day, 0),
        )
        for day in day_keys
    ]
    return FounderFlowReportRead(window_days=window_days, points=points)


async def escalate_stale_leads(
    db: AsyncSession,
    *,
    actor_org_id: int,
    actor_role: str,
    actor_user_id: int | None,
    contact_ids: list[int] | None = None,
    limit: int = 20,
) -> list[int]:
    limit = max(1, min(200, int(limit)))
    sla_cfg = await get_empire_sla_config(db, organization_id=actor_org_id)
    stale_days = int(sla_cfg.stale_unrouted_days)
    now = datetime.now(UTC)
    stale_cutoff = now - timedelta(days=stale_days)

    query = apply_contact_visibility_scope(
        select(Contact).where(Contact.routed_company_id.is_(None)),
        actor_org_id=actor_org_id,
        actor_role=actor_role,
    )
    if contact_ids:
        wanted = [int(c) for c in contact_ids if int(c) > 0]
        query = query.where(Contact.id.in_(wanted))
    result = await db.execute(query.order_by(Contact.created_at.asc()).limit(limit))
    contacts = list(result.scalars().all())

    workspace = await workspace_service.ensure_default_workspace(db, actor_org_id)
    candidate_contact_ids = [int(contact.id) for contact in contacts]
    existing_escalation_contact_ids: set[int] = set()
    if candidate_contact_ids:
        existing_rows = await db.execute(
            select(DecisionCard).where(
                DecisionCard.organization_id == actor_org_id,
                DecisionCard.source_type == "stale_lead_escalation",
                DecisionCard.source_id.in_([str(contact_id) for contact_id in candidate_contact_ids]),
                DecisionCard.status.in_(["pending", "deferred"]),
            )
        )
        existing_escalation_contact_ids = {
            int(card.source_id)
            for card in existing_rows.scalars().all()
            if str(card.source_id or "").isdigit()
        }
    card_ids: list[int] = []
    for contact in contacts:
        if int(contact.id) in existing_escalation_contact_ids:
            continue
        created_at = _normalize_dt(getattr(contact, "created_at", None))
        if created_at is None or created_at > stale_cutoff:
            continue
        card = await decision_card_service.create_decision_card(
            db,
            org_id=actor_org_id,
            proposed_by=actor_user_id,
            data=DecisionCardCreate(
                workspace_id=workspace.id,
                title=f"Escalate stale lead #{contact.id}: {contact.name[:100]}",
                context_summary=f"Lead is stale for >= {stale_days} day(s). Routing source={contact.routing_source or 'default'}.",
                options=[
                    DecisionOption(label="Route immediately", description="Assign to a target company now."),
                    DecisionOption(label="Disqualify lead", description="Close this lead as not viable."),
                ],
                recommendation="Route immediately",
                category="operational",
                urgency="high",
                source_type="stale_lead_escalation",
                source_id=str(contact.id),
            ),
        )
        card_ids.append(int(card.id))
    return card_ids
