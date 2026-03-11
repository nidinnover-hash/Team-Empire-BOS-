import logging
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.lead_routing import (
    EMPIRE_DIGITAL_COMPANY_ID,
    apply_contact_visibility_scope,
    is_valid_routing_transition,
    normalize_lead_type,
    normalize_routing_status,
    now_utc,
    resolve_routed_company_id,
)
from app.models.contact import PIPELINE_STAGES, Contact
from app.platform.signals import (
    CONTACT_CREATED,
    CONTACT_DELETED,
    CONTACT_ROUTED,
    CONTACT_UPDATED,
    SignalCategory,
    SignalEnvelope,
    publish_signal,
)
from app.schemas.contact import ContactCreate, ContactUpdate, PipelineSummary
from app.services import lead_routing_policy as routing_policy_service

logger = logging.getLogger(__name__)


async def _emit_contact_signal(
    db: AsyncSession, topic: str, org_id: int, contact: Contact,
    *, actor_user_id: int | None = None, extra: dict | None = None,
) -> None:
    try:
        payload = {"contact_id": contact.id, "name": contact.name, "email": contact.email}
        if extra:
            payload.update(extra)
        await publish_signal(
            SignalEnvelope(
                topic=topic,
                category=SignalCategory.DOMAIN,
                organization_id=org_id,
                actor_user_id=actor_user_id,
                source="contact.service",
                entity_type="contact",
                entity_id=str(contact.id),
                payload=payload,
            ),
            db=db,
        )
    except Exception:
        logger.debug("Signal emission failed for %s contact=%s", topic, contact.id, exc_info=True)


_UPDATE_FIELDS = {
    "name", "email", "phone", "company", "role", "relationship", "notes",
    "pipeline_stage", "lead_score", "lead_source", "deal_value",
    "lead_type", "source_channel", "campaign_name", "partner_id",
    "qualified_score", "qualified_status", "qualification_notes",
    "routing_status", "routing_reason", "routing_source", "routing_rule_id", "routed_company_id",
    "expected_close_date", "last_contacted_at", "next_follow_up_at", "tags",
}


async def create_contact(
    db: AsyncSession, data: ContactCreate, organization_id: int
) -> Contact:
    payload = data.model_dump()
    payload["lead_owner_company_id"] = EMPIRE_DIGITAL_COMPANY_ID
    payload["lead_type"] = normalize_lead_type(payload.get("lead_type"))
    payload["routing_status"] = "unrouted"
    payload["routing_reason"] = "new_lead_default"
    payload["routing_source"] = "default"
    payload["routing_rule_id"] = None
    payload["routed_company_id"] = None
    payload["routed_at"] = None
    payload["routed_by_user_id"] = None
    payload["qualified_score"] = None
    payload["qualified_status"] = "unqualified"
    payload["qualification_notes"] = None
    contact = Contact(**payload, organization_id=organization_id)
    db.add(contact)
    await db.commit()
    await db.refresh(contact)
    logger.info("contact created id=%d org=%d", contact.id, organization_id)
    await _emit_contact_signal(db, CONTACT_CREATED, organization_id, contact)
    return contact


async def list_contacts(
    db: AsyncSession,
    organization_id: int,
    *,
    actor_org_id: int | None = None,
    actor_role: str | None = None,
    limit: int = 100,
    offset: int = 0,
    pipeline_stage: str | None = None,
    lead_score_min: int | None = None,
    lead_score_max: int | None = None,
    relationship: str | None = None,
    search: str | None = None,
) -> list[Contact]:
    query = select(Contact).where(Contact.is_deleted.is_(False))
    if actor_org_id is not None and actor_role is not None:
        query = apply_contact_visibility_scope(query, actor_org_id=actor_org_id, actor_role=actor_role)
    else:
        query = query.where(Contact.organization_id == organization_id)
    if pipeline_stage:
        query = query.where(Contact.pipeline_stage == pipeline_stage)
    if lead_score_min is not None:
        query = query.where(Contact.lead_score >= lead_score_min)
    if lead_score_max is not None:
        query = query.where(Contact.lead_score <= lead_score_max)
    if relationship:
        query = query.where(Contact.relationship == relationship)
    if search:
        pattern = f"%{search}%"
        query = query.where(
            Contact.name.ilike(pattern)
            | Contact.email.ilike(pattern)
            | Contact.company.ilike(pattern)
        )
    result = await db.execute(
        query.order_by(Contact.name).offset(offset).limit(limit)
    )
    return list(result.scalars().all())


async def get_contact(
    db: AsyncSession,
    contact_id: int,
    organization_id: int,
    *,
    actor_org_id: int | None = None,
    actor_role: str | None = None,
) -> Contact | None:
    query = select(Contact).where(Contact.id == contact_id, Contact.is_deleted.is_(False))
    if actor_org_id is not None and actor_role is not None:
        query = apply_contact_visibility_scope(query, actor_org_id=actor_org_id, actor_role=actor_role)
    else:
        query = query.where(Contact.organization_id == organization_id)
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def update_contact(
    db: AsyncSession, contact_id: int, data: ContactUpdate, organization_id: int,
) -> Contact | None:
    contact = await get_contact(db, contact_id, organization_id)
    if contact is None:
        return None
    for field, value in data.model_dump(exclude_unset=True).items():
        if field in _UPDATE_FIELDS:
            setattr(contact, field, value)
    await db.commit()
    await db.refresh(contact)
    logger.info("contact updated id=%d org=%d", contact_id, organization_id)
    await _emit_contact_signal(db, CONTACT_UPDATED, organization_id, contact)
    return contact


async def delete_contact(
    db: AsyncSession, contact_id: int, organization_id: int,
) -> bool:
    """Soft-delete a contact. Returns True if deleted, False if not found."""
    from datetime import UTC
    from datetime import datetime as dt
    contact = await get_contact(db, contact_id, organization_id)
    if contact is None or contact.is_deleted:
        return False
    contact.is_deleted = True
    contact.deleted_at = dt.now(UTC)
    await db.commit()
    logger.info("contact soft-deleted id=%d org=%d", contact_id, organization_id)
    await _emit_contact_signal(db, CONTACT_DELETED, organization_id, contact)
    return True


async def get_follow_up_due(
    db: AsyncSession,
    organization_id: int,
    limit: int = 50,
    *,
    actor_org_id: int | None = None,
    actor_role: str | None = None,
) -> list[Contact]:
    """Contacts whose next_follow_up_at is in the past or today."""
    now = datetime.now(UTC)
    query = select(Contact).where(
        Contact.next_follow_up_at.isnot(None),
        Contact.next_follow_up_at <= now,
    )
    if actor_org_id is not None and actor_role is not None:
        query = apply_contact_visibility_scope(query, actor_org_id=actor_org_id, actor_role=actor_role)
    else:
        query = query.where(Contact.organization_id == organization_id)
    result = await db.execute(query.order_by(Contact.next_follow_up_at).limit(limit))
    return list(result.scalars().all())


async def get_pipeline_summary(
    db: AsyncSession,
    organization_id: int,
    *,
    actor_org_id: int | None = None,
    actor_role: str | None = None,
) -> list[PipelineSummary]:
    """Aggregate count + total deal value per pipeline stage."""
    query = select(
        Contact.pipeline_stage,
        func.count(Contact.id),
        func.coalesce(func.sum(Contact.deal_value), 0.0),
    )
    if actor_org_id is not None and actor_role is not None:
        query = apply_contact_visibility_scope(query, actor_org_id=actor_org_id, actor_role=actor_role)
    else:
        query = query.where(Contact.organization_id == organization_id)
    result = await db.execute(query.group_by(Contact.pipeline_stage))
    rows = result.all()
    stage_map = {row[0]: (row[1], row[2]) for row in rows}
    return [
        PipelineSummary(
            stage=stage,
            count=stage_map.get(stage, (0, 0.0))[0],
            total_deal_value=float(stage_map.get(stage, (0, 0.0))[1]),
        )
        for stage in PIPELINE_STAGES
    ]


async def route_contact(
    db: AsyncSession,
    *,
    contact_id: int,
    organization_id: int,
    actor_user_id: int,
    actor_org_id: int,
    actor_role: str,
    lead_type: str | None = None,
    routed_company_id: int | None = None,
    routing_reason: str | None = None,
) -> Contact | None:
    contact = await get_contact(
        db,
        contact_id,
        organization_id,
        actor_org_id=actor_org_id,
        actor_role=actor_role,
    )
    if contact is None:
        return None

    effective_lead_type = normalize_lead_type(lead_type or contact.lead_type)
    target_company_id, status = resolve_routed_company_id(
        lead_type=effective_lead_type,
        manual_company_id=routed_company_id,
    )
    routing_source = "manual" if routed_company_id is not None else "fallback"
    routing_rule_id: int | None = None
    rule_reason: str | None = None
    if routed_company_id is None:
        matched_rule = await routing_policy_service.resolve_rule_target(
            db,
            owner_company_id=contact.lead_owner_company_id,
            lead_type=effective_lead_type,
        )
        if matched_rule is not None:
            target_company_id = matched_rule.target_company_id
            status = "routed"
            routing_source = "rule"
            routing_rule_id = int(matched_rule.id)
            rule_reason = matched_rule.routing_reason or f"rule:{matched_rule.id}"

    contact.lead_type = effective_lead_type
    contact.routed_company_id = target_company_id
    next_status = normalize_routing_status(status)
    if not is_valid_routing_transition(contact.routing_status, next_status):
        raise ValueError("invalid_routing_transition")
    contact.routing_status = next_status
    contact.routing_reason = (routing_reason or rule_reason or ("auto_route:" + effective_lead_type))[:500]
    contact.routing_source = routing_source
    contact.routing_rule_id = routing_rule_id
    contact.routed_by_user_id = actor_user_id if target_company_id is not None else None
    contact.routed_at = now_utc() if target_company_id is not None else None
    contact.updated_at = now_utc()

    await db.commit()
    await db.refresh(contact)
    logger.info(
        "contact routed id=%d owner_company=%d target_company=%s status=%s",
        contact.id,
        contact.lead_owner_company_id,
        str(contact.routed_company_id),
        contact.routing_status,
    )
    await _emit_contact_signal(
        db, CONTACT_ROUTED, organization_id, contact,
        actor_user_id=actor_user_id,
        extra={"routing_status": contact.routing_status, "routed_company_id": contact.routed_company_id},
    )
    return contact


async def find_duplicates(
    db: AsyncSession,
    organization_id: int,
    *,
    limit: int = 50,
) -> list[dict]:
    """Find potential duplicate contacts by matching email or normalized phone.

    Returns groups of contacts that share the same email or phone number.
    Each group is a dict with 'match_field', 'match_value', and 'contacts' list.
    """

    dupes: list[dict] = []

    # Email duplicates
    email_q = (
        select(Contact.email, func.count(Contact.id).label("cnt"))
        .where(
            Contact.organization_id == organization_id,
            Contact.email.isnot(None),
            Contact.email != "",
        )
        .group_by(Contact.email)
        .having(func.count(Contact.id) > 1)
        .limit(limit)
    )
    email_result = await db.execute(email_q)
    for row in email_result.all():
        contacts_q = select(Contact).where(
            Contact.organization_id == organization_id,
            Contact.email == row[0],
        )
        contacts = list((await db.execute(contacts_q)).scalars().all())
        dupes.append({
            "match_field": "email",
            "match_value": row[0],
            "count": row[1],
            "contacts": [
                {"id": c.id, "name": c.name, "email": c.email, "phone": c.phone,
                 "pipeline_stage": c.pipeline_stage, "created_at": c.created_at.isoformat() if c.created_at else None}
                for c in contacts
            ],
        })

    # Phone duplicates
    phone_q = (
        select(Contact.phone, func.count(Contact.id).label("cnt"))
        .where(
            Contact.organization_id == organization_id,
            Contact.phone.isnot(None),
            Contact.phone != "",
        )
        .group_by(Contact.phone)
        .having(func.count(Contact.id) > 1)
        .limit(limit)
    )
    phone_result = await db.execute(phone_q)
    for row in phone_result.all():
        # Skip if already captured as email duplicate
        contacts_q = select(Contact).where(
            Contact.organization_id == organization_id,
            Contact.phone == row[0],
        )
        contacts = list((await db.execute(contacts_q)).scalars().all())
        dupes.append({
            "match_field": "phone",
            "match_value": row[0],
            "count": row[1],
            "contacts": [
                {"id": c.id, "name": c.name, "email": c.email, "phone": c.phone,
                 "pipeline_stage": c.pipeline_stage, "created_at": c.created_at.isoformat() if c.created_at else None}
                for c in contacts
            ],
        })

    return dupes


def _snapshot_contact(c: Contact) -> dict:
    """Capture key fields of a contact for merge history."""
    return {
        "id": c.id, "name": c.name, "email": c.email, "phone": c.phone,
        "company": c.company, "role": c.role, "relationship": c.relationship,
        "notes": c.notes, "pipeline_stage": c.pipeline_stage,
        "lead_score": c.lead_score, "lead_source": c.lead_source,
        "deal_value": float(c.deal_value) if c.deal_value else None,
        "tags": c.tags, "source_channel": c.source_channel,
        "campaign_name": c.campaign_name, "partner_id": c.partner_id,
    }


async def merge_contacts(
    db: AsyncSession,
    organization_id: int,
    primary_id: int,
    duplicate_ids: list[int],
    actor_user_id: int | None = None,
) -> Contact | None:
    """Merge duplicate contacts into a primary contact.

    Preserves the primary contact, merges non-null fields from duplicates
    (primary values take precedence), then deletes the duplicates.
    Saves merge history for undo capability.
    """
    from app.models.contact_merge_history import ContactMergeHistory

    primary = await get_contact(db, primary_id, organization_id)
    if primary is None:
        return None

    dupes = []
    for did in duplicate_ids:
        if did == primary_id:
            continue
        d = await get_contact(db, did, organization_id)
        if d:
            dupes.append(d)

    if not dupes:
        return primary

    # Snapshot primary before merge
    primary_before = _snapshot_contact(primary)

    # Merge: fill in blanks on primary from duplicates (first non-null wins)
    _MERGE_FIELDS = [
        "email", "phone", "company", "role", "notes", "lead_source",
        "deal_value", "source_channel", "campaign_name", "partner_id",
        "expected_close_date", "tags",
    ]
    for field in _MERGE_FIELDS:
        if getattr(primary, field) is None:
            for d in dupes:
                val = getattr(d, field)
                if val is not None:
                    setattr(primary, field, val)
                    break

    # Keep highest lead_score and deal_value
    for d in dupes:
        if d.lead_score > primary.lead_score:
            primary.lead_score = d.lead_score
        if d.deal_value and (primary.deal_value is None or d.deal_value > primary.deal_value):
            primary.deal_value = d.deal_value

    # Merge tags
    existing_tags = set((primary.tags or "").split(",")) if primary.tags else set()
    for d in dupes:
        if d.tags:
            existing_tags.update(d.tags.split(","))
    existing_tags.discard("")
    if existing_tags:
        primary.tags = ",".join(sorted(existing_tags))

    primary.updated_at = now_utc()

    # Save merge history for each duplicate, then delete
    for d in dupes:
        history = ContactMergeHistory(
            organization_id=organization_id,
            primary_contact_id=primary_id,
            merged_contact_id=d.id,
            merged_contact_snapshot=_snapshot_contact(d),
            primary_before_snapshot=primary_before,
            actor_user_id=actor_user_id,
        )
        db.add(history)
        await db.delete(d)

    await db.commit()
    await db.refresh(primary)
    logger.info(
        "Merged %d contacts into primary %d (org %d)",
        len(dupes), primary_id, organization_id,
    )
    return primary


async def get_merge_history(
    db: AsyncSession,
    organization_id: int,
    contact_id: int,
    limit: int = 50,
) -> list:
    """Get merge history for a contact."""
    from app.models.contact_merge_history import ContactMergeHistory

    result = await db.execute(
        select(ContactMergeHistory).where(
            ContactMergeHistory.organization_id == organization_id,
            ContactMergeHistory.primary_contact_id == contact_id,
        ).order_by(ContactMergeHistory.created_at.desc()).limit(limit)
    )
    return list(result.scalars().all())


async def unmerge_contact(
    db: AsyncSession,
    organization_id: int,
    merge_history_id: int,
) -> Contact | None:
    """Undo a merge by re-creating the deleted contact from snapshot."""
    from app.models.contact_merge_history import ContactMergeHistory

    result = await db.execute(
        select(ContactMergeHistory).where(
            ContactMergeHistory.id == merge_history_id,
            ContactMergeHistory.organization_id == organization_id,
            ContactMergeHistory.undone.is_(False),
        )
    )
    history = result.scalar_one_or_none()
    if history is None:
        return None

    snap = history.merged_contact_snapshot or {}
    restored = Contact(
        organization_id=organization_id,
        name=snap.get("name", "Restored Contact"),
        email=snap.get("email"),
        phone=snap.get("phone"),
        company=snap.get("company"),
        role=snap.get("role"),
        relationship=snap.get("relationship", "personal"),
        notes=snap.get("notes"),
        pipeline_stage=snap.get("pipeline_stage", "new"),
        lead_score=snap.get("lead_score", 0),
        lead_source=snap.get("lead_source"),
        deal_value=snap.get("deal_value"),
        tags=snap.get("tags"),
        source_channel=snap.get("source_channel"),
        campaign_name=snap.get("campaign_name"),
        partner_id=snap.get("partner_id"),
    )
    db.add(restored)
    history.undone = True
    await db.commit()
    await db.refresh(restored)
    logger.info(
        "Unmerged contact %d from primary %d (org %d)",
        restored.id, history.primary_contact_id, organization_id,
    )
    return restored


async def get_pipeline_analytics(
    db: AsyncSession,
    organization_id: int,
) -> dict:
    """Pipeline conversion analytics: stage counts, conversion rates, avg deal values."""
    # Stage counts and deal values
    stage_q = (
        select(
            Contact.pipeline_stage,
            func.count(Contact.id),
            func.coalesce(func.sum(Contact.deal_value), 0.0),
            func.coalesce(func.avg(Contact.deal_value), 0.0),
            func.coalesce(func.avg(Contact.lead_score), 0.0),
        )
        .where(Contact.organization_id == organization_id)
        .group_by(Contact.pipeline_stage)
    )
    result = await db.execute(stage_q)
    rows = {r[0]: {"count": r[1], "total_value": float(r[2]), "avg_value": round(float(r[3]), 2), "avg_score": round(float(r[4]), 1)} for r in result.all()}

    # Build funnel with conversion rates
    funnel = []
    prev_count = None
    for stage in PIPELINE_STAGES:
        data = rows.get(stage, {"count": 0, "total_value": 0.0, "avg_value": 0.0, "avg_score": 0.0})
        conversion = round((data["count"] / prev_count) * 100, 1) if prev_count and prev_count > 0 else None
        funnel.append({
            "stage": stage,
            **data,
            "conversion_rate": conversion,
        })
        prev_count = data["count"]

    # Overall metrics
    total_q = await db.execute(
        select(
            func.count(Contact.id),
            func.coalesce(func.sum(Contact.deal_value), 0.0),
        ).where(Contact.organization_id == organization_id)
    )
    total_row = total_q.one()

    won_q = await db.execute(
        select(func.coalesce(func.sum(Contact.deal_value), 0.0))
        .where(Contact.organization_id == organization_id, Contact.pipeline_stage == "won")
    )
    won_value = float(won_q.scalar() or 0.0)

    return {
        "funnel": funnel,
        "total_contacts": total_row[0] or 0,
        "total_pipeline_value": float(total_row[1] or 0.0),
        "won_value": won_value,
        "win_rate": round((rows.get("won", {}).get("count", 0) / max(total_row[0] or 1, 1)) * 100, 1),
    }


async def qualify_contact(
    db: AsyncSession,
    *,
    contact_id: int,
    organization_id: int,
    actor_org_id: int,
    actor_role: str,
    lead_type: str | None = None,
    qualified_score: int | None = None,
    qualified_status: str | None = None,
    qualification_notes: str | None = None,
    routing_status: str | None = None,
) -> Contact | None:
    contact = await get_contact(
        db,
        contact_id,
        organization_id,
        actor_org_id=actor_org_id,
        actor_role=actor_role,
    )
    if contact is None:
        return None

    if lead_type is not None:
        contact.lead_type = normalize_lead_type(lead_type)
    if qualified_score is not None:
        contact.qualified_score = max(0, min(100, int(qualified_score)))
    if qualified_status is not None:
        status = str(qualified_status).strip().lower()
        if status in {"unqualified", "qualified", "disqualified", "needs_review"}:
            contact.qualified_status = status
    if qualification_notes is not None:
        contact.qualification_notes = qualification_notes[:4000]
    if routing_status is not None:
        next_status = normalize_routing_status(routing_status)
        if not is_valid_routing_transition(contact.routing_status, next_status):
            raise ValueError("invalid_routing_transition")
        contact.routing_status = next_status
    if (
        contact.qualified_status == "qualified"
        and contact.routing_status == "unrouted"
        and is_valid_routing_transition(contact.routing_status, "under_review")
    ):
        contact.routing_status = "under_review"
    contact.updated_at = now_utc()

    await db.commit()
    await db.refresh(contact)
    logger.info(
        "contact qualified id=%d org=%d status=%s score=%s",
        contact.id,
        organization_id,
        contact.qualified_status,
        str(contact.qualified_score),
    )
    return contact
