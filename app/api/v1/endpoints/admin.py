"""Super-admin cross-org analytics endpoints."""
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_super_admin
from app.logs.audit import record_action
from app.models.approval import Approval
from app.models.ceo_control import SchedulerJobRun
from app.models.notification import Notification
from app.models.organization import Organization
from app.models.task import Task
from app.models.user import User
from app.schemas.admin import (
    AdminUserRead,
    AutonomyDryRunRead,
    AutonomyDryRunRequest,
    AutonomyGatesRead,
    AutonomyPolicyHistoryItemRead,
    AutonomyPolicyRead,
    AutonomyPolicyUpdate,
    AutonomyRolloutRead,
    AutonomyRolloutUpdate,
    AutonomyTemplateRead,
    OrgReadinessFleetItem,
    OrgReadinessReport,
    OrgSummary,
    ReadinessTrendPoint,
    ReadinessTrendRead,
)
from app.services import autonomy_policy
from app.services.org_readiness import build_org_readiness_report

router = APIRouter(prefix="/admin", tags=["Super Admin"])


async def _load_org_or_404(db: AsyncSession, org_id: int) -> Organization:
    org_result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = org_result.scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=404, detail="Organisation not found")
    return org


async def _build_org_readiness_report(db: AsyncSession, org: Organization) -> OrgReadinessReport:
    return await build_org_readiness_report(db, org)


@router.get("/orgs", response_model=list[OrgSummary])
async def list_all_orgs(
    db: AsyncSession = Depends(get_db),
    _actor: dict = Depends(require_super_admin),
) -> list[OrgSummary]:
    """List all organisations with aggregate metrics."""
    orgs_result = await db.execute(select(Organization).order_by(Organization.id))
    orgs = list(orgs_result.scalars().all())

    # Batch counts via subqueries
    user_counts_q = await db.execute(
        select(User.organization_id, func.count(User.id).label("cnt"))
        .group_by(User.organization_id)
    )
    task_counts_q = await db.execute(
        select(Task.organization_id, func.count(Task.id).label("cnt"))
        .group_by(Task.organization_id)
    )
    approval_counts_q = await db.execute(
        select(Approval.organization_id, func.count(Approval.id).label("cnt"))
        .group_by(Approval.organization_id)
    )

    user_map = {r.organization_id: r.cnt for r in user_counts_q}
    task_map = {r.organization_id: r.cnt for r in task_counts_q}
    approval_map = {r.organization_id: r.cnt for r in approval_counts_q}

    # last_activity_at = latest task updated_at or created_at per org
    last_task_q = await db.execute(
        select(Task.organization_id, func.max(Task.created_at).label("last_at"))
        .group_by(Task.organization_id)
    )
    last_map = {r.organization_id: r.last_at for r in last_task_q}

    return [
        OrgSummary(
            id=org.id,
            name=org.name,
            slug=org.slug,
            user_count=user_map.get(org.id, 0),
            task_count=task_map.get(org.id, 0),
            approval_count=approval_map.get(org.id, 0),
            last_activity_at=last_map.get(org.id),
        )
        for org in orgs
    ]


@router.get("/orgs/{org_id}/summary", response_model=OrgSummary)
async def org_summary(
    org_id: int,
    db: AsyncSession = Depends(get_db),
    _actor: dict = Depends(require_super_admin),
) -> OrgSummary:
    """Full summary for a single org."""
    org_result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = org_result.scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=404, detail="Organisation not found")

    user_count_q = await db.execute(
        select(func.count(User.id)).where(User.organization_id == org_id)
    )
    task_count_q = await db.execute(
        select(func.count(Task.id)).where(Task.organization_id == org_id)
    )
    approval_count_q = await db.execute(
        select(func.count(Approval.id)).where(Approval.organization_id == org_id)
    )
    last_task_q = await db.execute(
        select(func.max(Task.created_at)).where(Task.organization_id == org_id)
    )

    return OrgSummary(
        id=org.id,
        name=org.name,
        slug=org.slug,
        user_count=user_count_q.scalar() or 0,
        task_count=task_count_q.scalar() or 0,
        approval_count=approval_count_q.scalar() or 0,
        last_activity_at=last_task_q.scalar(),
    )


@router.get("/orgs/{org_id}/readiness", response_model=OrgReadinessReport)
async def org_readiness(
    org_id: int,
    db: AsyncSession = Depends(get_db),
    _actor: dict = Depends(require_super_admin),
) -> OrgReadinessReport:
    """Operational readiness score for running an org with high autonomy."""
    org = await _load_org_or_404(db, org_id)
    return await _build_org_readiness_report(db, org)


@router.get("/orgs/readiness", response_model=list[OrgReadinessFleetItem])
async def orgs_readiness(
    status: Literal["ready", "watch", "blocked"] | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    _actor: dict = Depends(require_super_admin),
) -> list[OrgReadinessFleetItem]:
    """Fleet-wide readiness ranking across all organisations."""
    orgs = list((await db.execute(select(Organization).order_by(Organization.id))).scalars().all())
    items: list[OrgReadinessFleetItem] = []
    for org in orgs:
        report = await _build_org_readiness_report(db, org)
        if status and report.status != status:
            continue
        items.append(
            OrgReadinessFleetItem(
                org_id=report.org_id,
                org_name=report.org_name,
                score=report.score,
                status=report.status,
                blocker_count=len(report.blockers),
                generated_at=report.generated_at,
            )
        )
    items.sort(key=lambda item: (item.score, -item.blocker_count), reverse=True)
    return items[:limit]


@router.get("/orgs/{org_id}/autonomy-gates", response_model=AutonomyGatesRead)
async def org_autonomy_gates(
    org_id: int,
    db: AsyncSession = Depends(get_db),
    _actor: dict = Depends(require_super_admin),
) -> AutonomyGatesRead:
    """Return which autonomy modes are allowed for this org right now."""
    org = await _load_org_or_404(db, org_id)
    report = await _build_org_readiness_report(db, org)
    evaluation = await autonomy_policy.evaluate_autonomy_modes(db, org=org)

    return AutonomyGatesRead(
        org_id=report.org_id,
        org_name=report.org_name,
        readiness_score=report.score,
        readiness_status=report.status,
        allowed_modes=evaluation["allowed_modes"],
        denied_modes=evaluation["denied_modes"],
        reasons=evaluation["reasons"],
        generated_at=report.generated_at,
    )


@router.get("/orgs/{org_id}/autonomy-policy", response_model=AutonomyPolicyRead)
async def get_org_autonomy_policy(
    org_id: int,
    db: AsyncSession = Depends(get_db),
    _actor: dict = Depends(require_super_admin),
) -> AutonomyPolicyRead:
    org = await _load_org_or_404(db, org_id)
    policy = await autonomy_policy.get_autonomy_policy(db, int(org.id))
    meta = await autonomy_policy.get_autonomy_policy_meta(db, int(org.id))
    return AutonomyPolicyRead.model_validate({**policy, **meta})


@router.get("/orgs/{org_id}/autonomy-policy/templates", response_model=list[AutonomyTemplateRead])
async def list_org_autonomy_policy_templates(
    org_id: int,
    db: AsyncSession = Depends(get_db),
    _actor: dict = Depends(require_super_admin),
) -> list[AutonomyTemplateRead]:
    await _load_org_or_404(db, org_id)
    return [AutonomyTemplateRead.model_validate(row) for row in autonomy_policy.list_policy_templates()]


@router.post("/orgs/{org_id}/autonomy-policy/templates/{template_id}", response_model=AutonomyPolicyRead)
async def apply_org_autonomy_policy_template(
    org_id: int,
    template_id: str,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_super_admin),
) -> AutonomyPolicyRead:
    org = await _load_org_or_404(db, org_id)
    template = autonomy_policy.get_policy_template(template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Autonomy policy template not found")
    policy_updates = dict(template["policy"]) if isinstance(template.get("policy"), dict) else {}
    updated = await autonomy_policy.update_autonomy_policy(
        db,
        organization_id=int(org.id),
        updates=policy_updates,
        updated_by_user_id=int(actor.get("id")) if actor.get("id") is not None else None,
        updated_by_email=str(actor.get("email") or "").strip().lower() or None,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Organisation not found")
    policy, meta = updated
    await record_action(
        db=db,
        event_type="autonomy_policy_template_applied",
        actor_user_id=int(actor["id"]),
        organization_id=int(org.id),
        entity_type="organization",
        entity_id=int(org.id),
        payload_json={"template_id": template.get("id")},
    )
    return AutonomyPolicyRead.model_validate({**policy, **meta})


@router.get("/orgs/{org_id}/autonomy-policy/history", response_model=list[AutonomyPolicyHistoryItemRead])
async def list_org_autonomy_policy_history(
    org_id: int,
    limit: int = Query(default=20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    _actor: dict = Depends(require_super_admin),
) -> list[AutonomyPolicyHistoryItemRead]:
    org = await _load_org_or_404(db, org_id)
    history = await autonomy_policy.get_autonomy_policy_history(db, int(org.id), limit=limit)
    return [AutonomyPolicyHistoryItemRead.model_validate(item) for item in history]


@router.patch("/orgs/{org_id}/autonomy-policy", response_model=AutonomyPolicyRead)
async def update_org_autonomy_policy(
    org_id: int,
    data: AutonomyPolicyUpdate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_super_admin),
) -> AutonomyPolicyRead:
    org = await _load_org_or_404(db, org_id)
    before = await autonomy_policy.get_autonomy_policy(db, int(org.id))
    incoming = data.model_dump(exclude_unset=True)
    updated = await autonomy_policy.update_autonomy_policy(
        db,
        organization_id=int(org.id),
        updates=incoming,
        updated_by_user_id=int(actor.get("id")) if actor.get("id") is not None else None,
        updated_by_email=str(actor.get("email") or "").strip().lower() or None,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Organisation not found")
    policy, meta = updated
    changed_fields = [key for key, value in incoming.items() if before.get(key) != value]
    await record_action(
        db=db,
        event_type="autonomy_policy_updated",
        actor_user_id=int(actor["id"]),
        organization_id=int(org.id),
        entity_type="organization",
        entity_id=int(org.id),
        payload_json={
            "changed_fields": changed_fields,
            "before": {k: before.get(k) for k in changed_fields},
            "after": {k: policy.get(k) for k in changed_fields},
        },
    )
    return AutonomyPolicyRead.model_validate({**policy, **meta})


@router.get("/orgs/{org_id}/autonomy-rollout", response_model=AutonomyRolloutRead)
async def get_org_autonomy_rollout(
    org_id: int,
    db: AsyncSession = Depends(get_db),
    _actor: dict = Depends(require_super_admin),
) -> AutonomyRolloutRead:
    org = await _load_org_or_404(db, org_id)
    rollout = await autonomy_policy.get_rollout_config(db, int(org.id))
    return AutonomyRolloutRead.model_validate(rollout)


@router.patch("/orgs/{org_id}/autonomy-rollout", response_model=AutonomyRolloutRead)
async def update_org_autonomy_rollout(
    org_id: int,
    data: AutonomyRolloutUpdate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_super_admin),
) -> AutonomyRolloutRead:
    org = await _load_org_or_404(db, org_id)
    updates = data.model_dump(exclude_unset=True)
    updated = await autonomy_policy.update_rollout_config(
        db,
        organization_id=int(org.id),
        updates=updates,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Organisation not found")
    await record_action(
        db=db,
        event_type="autonomy_rollout_updated",
        actor_user_id=int(actor["id"]),
        organization_id=int(org.id),
        entity_type="organization",
        entity_id=int(org.id),
        payload_json={"updated_fields": sorted(list(updates.keys()))},
    )
    return AutonomyRolloutRead.model_validate(updated)


@router.post("/orgs/{org_id}/autonomy-dry-run", response_model=AutonomyDryRunRead)
async def org_autonomy_dry_run(
    org_id: int,
    data: AutonomyDryRunRequest,
    db: AsyncSession = Depends(get_db),
    _actor: dict = Depends(require_super_admin),
) -> AutonomyDryRunRead:
    org = await _load_org_or_404(db, org_id)
    readiness = await _build_org_readiness_report(db, org)
    gates = await autonomy_policy.evaluate_autonomy_modes(db, org=org)
    rollout = await autonomy_policy.evaluate_rollout_for_execution(db, org=org)
    can_auto, auto_reason = await autonomy_policy.can_auto_approve(db, org=org)
    can_execute, execute_reason = await autonomy_policy.can_execute_post_approval(db, org=org)
    reasons = [reason for reason in [auto_reason, execute_reason] if reason]
    reasons.extend(gates["reasons"])
    # Deduplicate while preserving order.
    seen: set[str] = set()
    unique_reasons: list[str] = []
    for reason in reasons:
        if reason not in seen:
            seen.add(reason)
            unique_reasons.append(reason)
    return AutonomyDryRunRead(
        org_id=int(org.id),
        org_name=org.name,
        approval_type=(data.approval_type or "").strip(),
        readiness_score=readiness.score,
        readiness_status=readiness.status,
        allowed_modes=gates["allowed_modes"],
        rollout_allowed=rollout["allowed"],
        rollout_reason=rollout["reason"] or None,
        actions_today=rollout["actions_today"],
        max_actions_per_day=rollout["max_actions_per_day"],
        can_auto_approve=can_auto,
        can_execute_after_approval=can_execute,
        reasons=unique_reasons,
        generated_at=datetime.now(UTC),
    )


@router.post("/orgs/{org_id}/autonomy-policy/rollback/{version_id}", response_model=AutonomyPolicyRead)
async def rollback_org_autonomy_policy(
    org_id: int,
    version_id: str,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_super_admin),
) -> AutonomyPolicyRead:
    org = await _load_org_or_404(db, org_id)
    rolled_back = await autonomy_policy.rollback_autonomy_policy(
        db,
        organization_id=int(org.id),
        version_id=version_id,
        updated_by_user_id=int(actor.get("id")) if actor.get("id") is not None else None,
        updated_by_email=str(actor.get("email") or "").strip().lower() or None,
    )
    if rolled_back is None:
        raise HTTPException(status_code=404, detail="Autonomy policy version not found")
    policy, meta = rolled_back
    await record_action(
        db=db,
        event_type="autonomy_policy_rolled_back",
        actor_user_id=int(actor["id"]),
        organization_id=int(org.id),
        entity_type="organization",
        entity_id=int(org.id),
        payload_json={"version_id": version_id},
    )
    return AutonomyPolicyRead.model_validate({**policy, **meta})


@router.get("/orgs/{org_id}/readiness/trend", response_model=ReadinessTrendRead)
async def org_readiness_trend(
    org_id: int,
    days: int = Query(default=7, ge=1, le=30),
    db: AsyncSession = Depends(get_db),
    _actor: dict = Depends(require_super_admin),
) -> ReadinessTrendRead:
    """Historical risk trend from scheduler failures, high alerts, and approval load."""
    org = await _load_org_or_404(db, org_id)
    start_dt = datetime.now(UTC) - timedelta(days=days - 1)

    failure_rows = (
        await db.execute(
            select(func.date(SchedulerJobRun.started_at), func.count(SchedulerJobRun.id))
            .where(
                SchedulerJobRun.organization_id == org_id,
                SchedulerJobRun.started_at >= start_dt,
                SchedulerJobRun.status == "error",
            )
            .group_by(func.date(SchedulerJobRun.started_at))
        )
    ).all()
    high_alert_rows = (
        await db.execute(
            select(func.date(Notification.created_at), func.count(Notification.id))
            .where(
                Notification.organization_id == org_id,
                Notification.created_at >= start_dt,
                Notification.severity.in_(["high", "error", "critical"]),
            )
            .group_by(func.date(Notification.created_at))
        )
    ).all()
    pending_rows = (
        await db.execute(
            select(func.date(Approval.created_at), func.count(Approval.id))
            .where(
                Approval.organization_id == org_id,
                Approval.created_at >= start_dt,
                Approval.status == "pending",
            )
            .group_by(func.date(Approval.created_at))
        )
    ).all()

    fail_map = {str(day): int(count) for day, count in failure_rows}
    alert_map = {str(day): int(count) for day, count in high_alert_rows}
    pending_map = {str(day): int(count) for day, count in pending_rows}

    series: list[ReadinessTrendPoint] = []
    for offset in range(days):
        day = (start_dt + timedelta(days=offset)).date().isoformat()
        series.append(
            ReadinessTrendPoint(
                day=day,
                integration_failures=fail_map.get(day, 0),
                high_alerts_created=alert_map.get(day, 0),
                pending_approvals_created=pending_map.get(day, 0),
            )
        )

    return ReadinessTrendRead(
        org_id=org.id,
        org_name=org.name,
        days=days,
        series=series,
        generated_at=datetime.now(UTC),
    )


@router.get("/users", response_model=list[AdminUserRead])
async def list_all_users(
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _actor: dict = Depends(require_super_admin),
) -> list[AdminUserRead]:
    """All users across all orgs (paginated)."""
    result = await db.execute(
        select(User).order_by(User.organization_id, User.id).limit(limit).offset(offset)
    )
    users = list(result.scalars().all())
    return [AdminUserRead.model_validate(user) for user in users]


@router.post("/users/{user_id}/grant-super", status_code=200)
async def grant_super_admin(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_super_admin),
) -> dict:
    """Grant super-admin to a user."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_super_admin = True
    await db.commit()
    return {"ok": True, "user_id": user_id, "is_super_admin": True}


@router.post("/users/{user_id}/revoke-super", status_code=200)
async def revoke_super_admin(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_super_admin),
) -> dict:
    """Revoke super-admin from a user. Cannot revoke from self."""
    if actor.get("id") == user_id:
        raise HTTPException(status_code=400, detail="Cannot revoke your own super-admin access")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_super_admin = False
    await db.commit()
    return {"ok": True, "user_id": user_id, "is_super_admin": False}
