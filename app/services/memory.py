"""
Memory service — manages profile memory, team members, and daily context.

The most important function here is build_memory_context() which assembles
everything into a single string that gets injected into every AI call.
"""

import logging
from collections.abc import Mapping
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.memory.retrieval import (
    DEFAULT_CONTEXT_CHAR_LIMIT,
    build_focused_context,
    build_typed_context,
)
from app.models.memory import AvatarMemory, DailyContext, ProfileMemory, TeamMember
from app.schemas.memory import (
    DailyContextCreate,
    TeamMemberCreate,
    TeamMemberUpdate,
)

logger = logging.getLogger(__name__)

# ── Profile Memory ────────────────────────────────────────────────────────────

async def get_profile_memory(
    db: AsyncSession, organization_id: int
) -> list[ProfileMemory]:
    now = datetime.now(UTC)
    result = await db.execute(
        select(ProfileMemory)
        .where(
            ProfileMemory.organization_id == organization_id,
            (ProfileMemory.expires_at.is_(None)) | (ProfileMemory.expires_at > now),
        )
        .order_by(ProfileMemory.category, ProfileMemory.key)
        .limit(500)
    )
    return list(result.scalars().all())


async def get_avatar_memory(
    db: AsyncSession,
    organization_id: int,
    avatar_mode: str,
) -> list[AvatarMemory]:
    lowered = str(avatar_mode).strip().lower()
    mode = lowered if lowered in {"personal", "professional", "entertainment", "strategy"} else "professional"
    result = await db.execute(
        select(AvatarMemory)
        .where(
            AvatarMemory.organization_id == organization_id,
            AvatarMemory.avatar_mode == mode,
        )
        .order_by(AvatarMemory.key)
        .limit(500)
    )
    return list(result.scalars().all())


async def upsert_avatar_memory(
    db: AsyncSession,
    organization_id: int,
    avatar_mode: str,
    key: str,
    value: str,
) -> AvatarMemory:
    """Create or update an avatar-scoped memory entry."""
    result = await db.execute(
        select(AvatarMemory).where(
            AvatarMemory.organization_id == organization_id,
            AvatarMemory.avatar_mode == avatar_mode,
            AvatarMemory.key == key,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        existing.value = value
        existing.updated_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(existing)
        return existing

    new_entry = AvatarMemory(
        organization_id=organization_id,
        avatar_mode=avatar_mode,
        key=key,
        value=value,
    )
    db.add(new_entry)
    try:
        await db.commit()
        await db.refresh(new_entry)
    except IntegrityError:
        await db.rollback()
        retry = await db.execute(
            select(AvatarMemory).where(
                AvatarMemory.organization_id == organization_id,
                AvatarMemory.avatar_mode == avatar_mode,
                AvatarMemory.key == key,
            )
        )
        existing = retry.scalar_one_or_none()
        if existing is None:
            raise
        existing.value = value
        existing.updated_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(existing)
        return existing
    return new_entry


async def upsert_profile_memory(
    db: AsyncSession,
    organization_id: int,
    key: str,
    value: str,
    category: str | None = None,
) -> ProfileMemory:
    """Create or update a profile memory entry by key.

    Handles the TOCTOU race: if two concurrent calls both pass the SELECT,
    the INSERT that loses gets an IntegrityError and retries as an UPDATE.
    """
    result = await db.execute(
        select(ProfileMemory).where(
            ProfileMemory.organization_id == organization_id,
            ProfileMemory.key == key,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.value = value
        existing.category = category
        existing.updated_at = datetime.now(UTC)
        try:
            await db.commit()
            await db.refresh(existing)
        except SQLAlchemyError:
            await db.rollback()
            raise
        return existing

    new_entry = ProfileMemory(
        organization_id=organization_id,
        key=key,
        value=value,
        category=category,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db.add(new_entry)
    try:
        await db.commit()
        await db.refresh(new_entry)
    except IntegrityError:
        # Concurrent insert won the race — retry as update
        await db.rollback()
        retry = await db.execute(
            select(ProfileMemory).where(
                ProfileMemory.organization_id == organization_id,
                ProfileMemory.key == key,
            )
        )
        existing = retry.scalar_one_or_none()
        if existing is None:
            raise  # re-raise IntegrityError if the winning row vanished
        existing.value = value
        existing.category = category
        existing.updated_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(existing)
        return existing
    except SQLAlchemyError:
        await db.rollback()
        raise
    return new_entry


async def delete_profile_memory(
    db: AsyncSession, entry_id: int, organization_id: int
) -> bool:
    """Delete a profile memory entry by ID. Returns True if it existed and was deleted."""
    result = await db.execute(
        select(ProfileMemory).where(
            ProfileMemory.id == entry_id,
            ProfileMemory.organization_id == organization_id,
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        return False
    await db.delete(entry)
    try:
        await db.commit()
    except SQLAlchemyError:
        await db.rollback()
        raise
    return True


# ── Team Members ──────────────────────────────────────────────────────────────

async def get_team_members(
    db: AsyncSession,
    organization_id: int,
    team: str | None = None,
    active_only: bool = True,
) -> list[TeamMember]:
    query = select(TeamMember).where(TeamMember.organization_id == organization_id)
    if team:
        query = query.where(TeamMember.team == team)
    if active_only:
        query = query.where(TeamMember.is_active.is_(True))
    query = query.order_by(TeamMember.team, TeamMember.name)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_team_member(
    db: AsyncSession, member_id: int, organization_id: int
) -> TeamMember | None:
    result = await db.execute(
        select(TeamMember).where(
            TeamMember.id == member_id,
            TeamMember.organization_id == organization_id,
        )
    )
    return result.scalar_one_or_none()


async def create_team_member(
    db: AsyncSession, data: TeamMemberCreate, organization_id: int
) -> TeamMember:
    member = TeamMember(
        organization_id=organization_id,
        name=data.name,
        role_title=data.role_title,
        team=data.team,
        reports_to_id=data.reports_to_id,
        skills=data.skills,
        ai_level=data.ai_level,
        current_project=data.current_project,
        notes=data.notes,
        user_id=data.user_id,
        created_at=datetime.now(UTC),
    )
    db.add(member)
    await db.commit()
    await db.refresh(member)
    return member


async def update_team_member(
    db: AsyncSession,
    member_id: int,
    organization_id: int,
    data: TeamMemberUpdate,
) -> TeamMember | None:
    member = await get_team_member(db, member_id, organization_id)
    if not member:
        return None
    _ALLOWED_FIELDS = {
        "role_title", "team", "reports_to_id", "skills",
        "ai_level", "current_project", "notes", "is_active",
    }
    for field, val in data.model_dump(exclude_unset=True).items():
        if field in _ALLOWED_FIELDS:
            setattr(member, field, val)
    await db.commit()
    await db.refresh(member)
    return member


# ── Daily Context ─────────────────────────────────────────────────────────────

async def get_daily_context(
    db: AsyncSession,
    organization_id: int,
    for_date: date | None = None,
) -> list[DailyContext]:
    target = for_date or date.today()
    result = await db.execute(
        select(DailyContext)
        .where(
            DailyContext.organization_id == organization_id,
            DailyContext.date == target,
        )
        .order_by(DailyContext.context_type, DailyContext.created_at)
        .limit(500)
    )
    return list(result.scalars().all())


async def add_daily_context(
    db: AsyncSession, data: DailyContextCreate, organization_id: int
) -> DailyContext:
    entry = DailyContext(
        organization_id=organization_id,
        date=data.date,
        context_type=data.context_type,
        content=data.content,
        related_to=data.related_to,
        created_at=datetime.now(UTC),
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


# ── Memory Context Cache ─────────────────────────────────────────────────────
_memory_context_cache: dict[int, tuple[float, str]] = {}
_memory_context_cache_stats: dict[str, int] = {
    "hits": 0,
    "misses": 0,
    "stale_pruned": 0,
    "evictions": 0,
    "size": 0,
}


def invalidate_memory_cache(organization_id: int) -> None:
    """Clear cached memory context for an org (call after memory writes)."""
    _memory_context_cache.pop(organization_id, None)
    _memory_context_cache_stats["size"] = len(_memory_context_cache)


def get_memory_cache_stats() -> dict[str, int]:
    stats = dict(_memory_context_cache_stats)
    stats["size"] = len(_memory_context_cache)
    return stats


def _prune_memory_cache(now_ts: float, ttl_seconds: int, max_orgs: int) -> None:
    stale_orgs = [
        org_id for org_id, (ts, _ctx) in _memory_context_cache.items()
        if now_ts - ts >= ttl_seconds
    ]
    for org_id in stale_orgs:
        _memory_context_cache.pop(org_id, None)
    _memory_context_cache_stats["stale_pruned"] += len(stale_orgs)
    # Enforce bounded cache size.
    while len(_memory_context_cache) >= max_orgs and _memory_context_cache:
        oldest_org = min(_memory_context_cache.items(), key=lambda item: item[1][0])[0]
        _memory_context_cache.pop(oldest_org, None)
        _memory_context_cache_stats["evictions"] += 1
    _memory_context_cache_stats["size"] = len(_memory_context_cache)


# ── Memory Context Builder ────────────────────────────────────────────────────

async def build_memory_context(
    db: AsyncSession,
    organization_id: int,
    categories: list[str] | None = None,
    char_limit: int = DEFAULT_CONTEXT_CHAR_LIMIT,
) -> str:
    """
    Assemble memory into a trimmed string for AI injection.

    Uses build_focused_context() from app/memory/retrieval.py to:
    - Optionally filter profile entries by category
    - Automatically trim to char_limit to prevent context bloat

    This is what makes the clone feel like Nidin — it knows who he is,
    who his team is, and what's happening today.
    """
    import time as _time
    ttl_seconds = int(settings.MEMORY_CONTEXT_CACHE_TTL_SECONDS)
    max_orgs = int(settings.MEMORY_CONTEXT_CACHE_MAX_ORGS)
    # Return cached context if fresh.
    cached = _memory_context_cache.get(organization_id)
    if cached and categories is None and char_limit == DEFAULT_CONTEXT_CHAR_LIMIT:
        ts, ctx = cached
        if _time.time() - ts < ttl_seconds:
            _memory_context_cache_stats["hits"] += 1
            return ctx
    if categories is None and char_limit == DEFAULT_CONTEXT_CHAR_LIMIT:
        _memory_context_cache_stats["misses"] += 1

    import asyncio as _asyncio

    from sqlalchemy import select as _select

    from app.models.task import Task as _Task
    from app.services.integration import list_integrations as _list_integrations

    profile, members, today_context, integrations = await _asyncio.gather(
        get_profile_memory(db, organization_id=organization_id),
        get_team_members(db, organization_id=organization_id, active_only=True),
        get_daily_context(db, organization_id=organization_id, for_date=date.today()),
        _list_integrations(db, organization_id=organization_id),
    )
    integration_statuses: list[Mapping[str, object]] = [
        {
            "type": item.type,
            "status": item.status,
            "last_sync_at": item.last_sync_at.isoformat() if item.last_sync_at else None,
        }
        for item in integrations
    ]

    base_context = build_focused_context(
        profile_entries=profile,
        team_members=members,
        daily_contexts=today_context,
        categories=categories,
        char_limit=char_limit,
    )

    # Reuse typed context assembly so integration layer stays populated in live AI flows.
    typed_layers = build_typed_context(
        profile_entries=profile,
        team_members=members,
        daily_contexts=today_context,
        integration_statuses=integration_statuses,
        categories=categories,
        char_limit=char_limit,
    )
    integration_layer = next((layer for layer in typed_layers if layer.get("layer_type") == "integration"), None)
    if integration_layer and integration_layer.get("content"):
        integration_block = str(integration_layer["content"])
        remaining = char_limit - len(base_context)
        if remaining > 100:
            base_context = base_context + "\n\n" + integration_block[:remaining]

    # Single query for all external tasks (ClickUp + GitHub PRs + GitHub issues)
    ext_result = await db.execute(
        _select(_Task).where(
            _Task.organization_id == organization_id,
            _Task.external_source.in_(["clickup", "github_pr", "github_issue"]),
            _Task.is_done.is_(False),
        ).order_by(_Task.priority.desc()).limit(45)
    )
    ext_tasks = list(ext_result.scalars().all())

    cu_tasks = [t for t in ext_tasks if t.external_source == "clickup"][:20]
    gh_prs = [t for t in ext_tasks if t.external_source == "github_pr"][:15]
    gh_issues = [t for t in ext_tasks if t.external_source == "github_issue"][:10]

    if cu_tasks:
        lines = ["[CLICKUP OPEN TASKS]"]
        for t in cu_tasks:
            due = f" (due {t.due_date})" if t.due_date else ""
            lines.append(f"- {t.title}{due}")
        lines.append("[END CLICKUP TASKS]")
        clickup_block = "\n".join(lines)
        remaining = char_limit - len(base_context)
        if remaining > 100:
            base_context = base_context + "\n\n" + clickup_block[:remaining]

    if gh_prs or gh_issues:
        lines = ["[GITHUB DEV ACTIVITY]"]
        if gh_prs:
            lines.append(f"Open PRs ({len(gh_prs)}):")
            for t in gh_prs:
                lines.append(f"  • {t.title}")
        if gh_issues:
            lines.append(f"Open bug issues ({len(gh_issues)}):")
            for t in gh_issues:
                lines.append(f"  • {t.title}")
        lines.append("[END GITHUB]")
        github_block = "\n".join(lines)
        remaining = char_limit - len(base_context)
        if remaining > 100:
            base_context = base_context + "\n\n" + github_block[:remaining]

    # ── Work pattern feedback loop ──
    # Inject ops intelligence patterns so the AI reasons about real work data.
    from app.services.pattern_analysis import build_work_patterns_context
    try:
        patterns_block = await build_work_patterns_context(db, organization_id, weeks=2)
        if patterns_block:
            remaining = char_limit - len(base_context)
            if remaining > 200:
                base_context = base_context + "\n\n" + patterns_block[:remaining]
    except (RuntimeError, ValueError, TypeError, TimeoutError, AttributeError) as exc:
        logger.warning(
            "Skipping work pattern context org=%s due to %s",
            organization_id,
            type(exc).__name__,
        )

    # ── Threat intelligence context ──
    try:
        from app.services.data_collection import get_threat_layer_report
        threat_report = await get_threat_layer_report(db, organization_id)
        if threat_report.total_signals_7d > 0:
            threat_lines = [
                "[SECURITY POSTURE]",
                f"Security Score: {threat_report.security_score}/100",
                f"Threats (7d): {threat_report.total_signals_7d}",
                f"Active Policies: {threat_report.active_policies}",
            ]
            if threat_report.top_threats:
                threat_lines.append("Top threats:")
                for threat in threat_report.top_threats[:3]:
                    threat_lines.append(f"  - [{threat.severity}] {threat.title}")
            if threat_report.recommendations:
                threat_lines.append(f"Action: {threat_report.recommendations[0]}")
            threat_lines.append("[END SECURITY]")
            threat_block = "\n".join(threat_lines)
            remaining = char_limit - len(base_context)
            if remaining > 150:
                base_context = base_context + "\n\n" + threat_block[:remaining]
    except (RuntimeError, ValueError, TypeError, TimeoutError, AttributeError) as exc:
        logger.warning(
            "Skipping threat intelligence context org=%s due to %s",
            organization_id,
            type(exc).__name__,
        )

    # ── Stripe financial context ──
    try:
        from app.services.stripe_service import get_financial_summary
        fin = await get_financial_summary(db, organization_id)
        if fin.get("connected") and fin.get("total_charges", 0) > 0:
            fin_lines = [
                "[STRIPE FINANCIALS]",
                f"Charges (30d): {fin['total_charges']}",
                f"Revenue: ${fin['total_revenue_usd']}",
                f"Refunded: ${fin['total_refunded_usd']}",
                f"Open disputes: {fin.get('disputes_open', 0)}",
                "[END STRIPE]",
            ]
            fin_block = "\n".join(fin_lines)
            remaining = char_limit - len(base_context)
            if remaining > 100:
                base_context = base_context + "\n\n" + fin_block[:remaining]
    except (RuntimeError, ValueError, TypeError, TimeoutError, AttributeError) as exc:
        logger.warning(
            "Skipping stripe financial context org=%s due to %s",
            organization_id,
            type(exc).__name__,
        )

    # ── Calendly upcoming events context ──
    try:
        from app.services.integration import get_integration_by_type as _get_int_by_type
        cal_int = await _get_int_by_type(db, organization_id, "calendly")
        if cal_int and cal_int.status == "connected":
            from sqlalchemy import select as _sel_dc
            cal_result = await db.execute(
                _sel_dc(DailyContext).where(
                    DailyContext.organization_id == organization_id,
                    DailyContext.context_type == "calendly_event",
                    DailyContext.date == date.today(),
                ).limit(10)
            )
            cal_events = list(cal_result.scalars().all())
            if cal_events:
                cal_lines = ["[CALENDLY TODAY]"]
                for ev in cal_events[:5]:
                    cal_lines.append(f"- {ev.content}")
                cal_lines.append("[END CALENDLY]")
                cal_block = "\n".join(cal_lines)
                remaining = char_limit - len(base_context)
                if remaining > 100:
                    base_context = base_context + "\n\n" + cal_block[:remaining]
    except (RuntimeError, ValueError, TypeError, TimeoutError, AttributeError) as exc:
        logger.warning(
            "Skipping calendly context org=%s due to %s",
            organization_id,
            type(exc).__name__,
        )

    # ── Character study traits ──
    char_traits = [
        p for p in profile
        if getattr(p, "category", None) == "character_study"
        and getattr(p, "key", "").startswith("character.study.summary")
    ]
    if char_traits:
        trait_lines = ["[CHARACTER PROFILE]"]
        for ct in char_traits[:3]:
            trait_lines.append(f"- {ct.value}")
        trait_lines.append("[END CHARACTER]")
        trait_block = "\n".join(trait_lines)
        remaining = char_limit - len(base_context)
        if remaining > 100:
            base_context = base_context + "\n\n" + trait_block[:remaining]

    # ── HubSpot deals pipeline ──
    try:
        from app.models.note import Note as _Note
        hs_result = await db.execute(
            _select(_Note).where(
                _Note.organization_id == organization_id,
                _Note.source == "hubspot_deal",
            ).order_by(_Note.created_at.desc()).limit(10)
        )
        hs_deals = list(hs_result.scalars().all())
        if hs_deals:
            deal_lines = ["[HUBSPOT CRM DEALS]"]
            for d in hs_deals[:8]:
                deal_lines.append(f"- {d.title or 'Unnamed'}: {(d.content or '')[:80]}")
            deal_lines.append("[END HUBSPOT DEALS]")
            deal_block = "\n".join(deal_lines)
            remaining = char_limit - len(base_context)
            if remaining > 100:
                base_context = base_context + "\n\n" + deal_block[:remaining]
    except (RuntimeError, ValueError, TypeError, TimeoutError, AttributeError) as exc:
        logger.warning("Skipping HubSpot deals context org=%s: %s", organization_id, type(exc).__name__)

    # ── Recent emails ──
    try:
        from app.models.email import Email as _Email
        email_result = await db.execute(
            _select(_Email).where(
                _Email.organization_id == organization_id,
            ).order_by(_Email.received_at.desc()).limit(8)
        )
        recent_emails = list(email_result.scalars().all())
        if recent_emails:
            email_lines = ["[RECENT EMAILS]"]
            for em in recent_emails[:5]:
                subj = getattr(em, "subject", "") or "No subject"
                sender = getattr(em, "from_address", "") or ""
                email_lines.append(f"- From: {sender[:40]} | {subj[:60]}")
            email_lines.append("[END EMAILS]")
            email_block = "\n".join(email_lines)
            remaining = char_limit - len(base_context)
            if remaining > 100:
                base_context = base_context + "\n\n" + email_block[:remaining]
    except (RuntimeError, ValueError, TypeError, TimeoutError, AttributeError) as exc:
        logger.warning("Skipping email context org=%s: %s", organization_id, type(exc).__name__)

    # ── Slack recent messages ──
    try:
        slack_result = await db.execute(
            _select(DailyContext).where(
                DailyContext.organization_id == organization_id,
                DailyContext.context_type == "slack",
            ).order_by(DailyContext.date.desc()).limit(8)
        )
        slack_msgs = list(slack_result.scalars().all())
        if slack_msgs:
            slack_lines = ["[SLACK RECENT]"]
            for sm in slack_msgs[:5]:
                channel = getattr(sm, "related_to", "") or ""
                body = (getattr(sm, "content", "") or "")[:80]
                slack_lines.append(f"- #{channel}: {body}")
            slack_lines.append("[END SLACK]")
            slack_block = "\n".join(slack_lines)
            remaining = char_limit - len(base_context)
            if remaining > 100:
                base_context = base_context + "\n\n" + slack_block[:remaining]
    except (RuntimeError, ValueError, TypeError, TimeoutError, AttributeError) as exc:
        logger.warning("Skipping slack context org=%s: %s", organization_id, type(exc).__name__)

    # ── WhatsApp conversations ──
    try:
        from app.models.whatsapp_message import WhatsAppMessage as _WaMsg
        wa_result = await db.execute(
            _select(_WaMsg).where(
                _WaMsg.organization_id == organization_id,
            ).order_by(_WaMsg.created_at.desc()).limit(8)
        )
        wa_msgs = list(wa_result.scalars().all())
        if wa_msgs:
            wa_lines = ["[WHATSAPP RECENT]"]
            for wm in wa_msgs[:5]:
                sender = getattr(wm, "from_number", "") or ""
                body = (getattr(wm, "body_text", "") or "")[:60]
                wa_lines.append(f"- {sender}: {body}")
            wa_lines.append("[END WHATSAPP]")
            wa_block = "\n".join(wa_lines)
            remaining = char_limit - len(base_context)
            if remaining > 100:
                base_context = base_context + "\n\n" + wa_block[:remaining]
    except (RuntimeError, ValueError, TypeError, TimeoutError, AttributeError) as exc:
        logger.warning("Skipping WhatsApp context org=%s: %s", organization_id, type(exc).__name__)

    # ── Google Analytics traffic ──
    try:
        from app.services.integration import get_integration_by_type as _get_ga_int
        ga_int = await _get_ga_int(db, organization_id, "google_analytics")
        if ga_int and ga_int.status == "connected":
            ga_ctx = await db.execute(
                _select(DailyContext).where(
                    DailyContext.organization_id == organization_id,
                    DailyContext.context_type == "google_analytics",
                ).order_by(DailyContext.date.desc()).limit(1)
            )
            ga_entry = ga_ctx.scalar_one_or_none()
            if ga_entry:
                ga_block = f"[GOOGLE ANALYTICS]\n{(ga_entry.content or '')[:300]}\n[END ANALYTICS]"
                remaining = char_limit - len(base_context)
                if remaining > 100:
                    base_context = base_context + "\n\n" + ga_block[:remaining]
    except (RuntimeError, ValueError, TypeError, TimeoutError, AttributeError) as exc:
        logger.warning("Skipping GA context org=%s: %s", organization_id, type(exc).__name__)

    # Cache the result for subsequent requests (skip if category-filtered or custom limit)
    if categories is None and char_limit == DEFAULT_CONTEXT_CHAR_LIMIT:
        now_ts = _time.time()
        _prune_memory_cache(now_ts, ttl_seconds=ttl_seconds, max_orgs=max_orgs)
        _memory_context_cache[organization_id] = (now_ts, base_context)
        _memory_context_cache_stats["size"] = len(_memory_context_cache)

    return base_context
