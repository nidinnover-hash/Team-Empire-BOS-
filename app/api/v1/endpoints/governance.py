from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.logs.audit import record_action
from app.schemas.governance import (
    AutomationLevel,
    ComplianceSummary,
    GovernancePolicyCreate,
    GovernancePolicyRead,
    GovernancePolicyUpdate,
    GovernanceViolationRead,
    PolicyDriftReportRead,
    PolicyDriftTrendPointRead,
    PolicyDriftTrendRead,
)
from app.services import governance as gov_service
from app.services import trend_telemetry

router = APIRouter(prefix="/governance", tags=["Governance"])


@router.post("/policies", response_model=GovernancePolicyRead, status_code=201)
async def create_policy(
    data: GovernancePolicyCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO")),
) -> GovernancePolicyRead:
    policy = await gov_service.create_policy(
        db, org_id=int(user["org_id"]), data=data, created_by=int(user["id"]),
    )
    await record_action(
        db,
        event_type="governance_policy_created",
        actor_user_id=user["id"],
        organization_id=user["org_id"],
        entity_type="governance_policy",
        entity_id=policy.id,
        payload_json={"name": policy.name, "type": policy.policy_type},
    )
    return policy


@router.get("/policies", response_model=list[GovernancePolicyRead])
async def list_policies(
    active_only: bool = Query(True),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> list[GovernancePolicyRead]:
    return await gov_service.list_policies(
        db, org_id=int(user["org_id"]), active_only=active_only, skip=skip, limit=limit,
    )


@router.patch("/policies/{policy_id}", response_model=GovernancePolicyRead)
async def update_policy(
    policy_id: int,
    data: GovernancePolicyUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO")),
) -> GovernancePolicyRead:
    policy = await gov_service.update_policy(
        db, org_id=int(user["org_id"]), policy_id=policy_id, data=data,
    )
    if policy is None:
        raise HTTPException(status_code=404, detail="Policy not found")
    await record_action(
        db,
        event_type="governance_policy_updated",
        actor_user_id=user["id"],
        organization_id=user["org_id"],
        entity_type="governance_policy",
        entity_id=policy.id,
        payload_json={"name": policy.name},
    )
    return policy


@router.post("/evaluate", response_model=list[dict])
async def evaluate_compliance(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> list[dict]:
    violations = await gov_service.evaluate_compliance(
        db, org_id=int(user["org_id"]),
    )
    await record_action(
        db,
        event_type="compliance_evaluated",
        actor_user_id=user["id"],
        organization_id=user["org_id"],
        entity_type="governance",
        entity_id=None,
        payload_json={"violations_found": len(violations)},
    )
    return violations


@router.get("/violations", response_model=list[GovernanceViolationRead])
async def list_violations(
    status: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> list[GovernanceViolationRead]:
    return await gov_service.list_violations(
        db, org_id=int(user["org_id"]), status=status, skip=skip, limit=limit,
    )


@router.post("/violations/{violation_id}/resolve", response_model=GovernanceViolationRead)
async def resolve_violation(
    violation_id: int,
    status: Literal["resolved", "dismissed"] = Query("resolved"),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO")),
) -> GovernanceViolationRead:
    violation = await gov_service.resolve_violation(
        db, org_id=int(user["org_id"]), violation_id=violation_id,
        resolved_by=int(user["id"]), status=status,
    )
    if violation is None:
        raise HTTPException(status_code=404, detail="Violation not found")
    await record_action(
        db,
        event_type="governance_violation_resolved",
        actor_user_id=user["id"],
        organization_id=user["org_id"],
        entity_type="governance_violation",
        entity_id=violation.id,
        payload_json={"status": status},
    )
    return violation


@router.get("/dashboard", response_model=ComplianceSummary)
async def governance_dashboard(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> ComplianceSummary:
    return await gov_service.get_governance_dashboard(
        db, org_id=int(user["org_id"]),
    )


@router.get("/automation-level", response_model=AutomationLevel)
async def get_automation_level(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> AutomationLevel:
    """Get the current progressive automation level for the organization."""
    return await gov_service.calculate_automation_level(
        db, org_id=int(user["org_id"]),
    )


@router.get("/policy-drift", response_model=PolicyDriftReportRead)
async def get_policy_drift(
    window_days: int = Query(14, ge=14, le=90),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> PolicyDriftReportRead:
    org_id = int(user["org_id"])
    report = await gov_service.detect_policy_drift(
        db,
        org_id=org_id,
        window_days=window_days,
    )
    trend_payload = trend_telemetry.compute_policy_drift_payload(report, window_days=window_days)
    await trend_telemetry.record_trend_event(
        db,
        org_id=org_id,
        event_type=trend_telemetry.GOVERNANCE_EVENT,
        payload_json=trend_payload,
        actor_user_id=int(user["id"]),
        entity_type="governance",
        throttle_minutes=15,
    )
    return PolicyDriftReportRead.model_validate(report)


@router.get("/policy-drift/trend", response_model=PolicyDriftTrendRead)
async def get_policy_drift_trend(
    limit: int = Query(14, ge=2, le=60),
    cursor: str | None = Query(None, max_length=128),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> PolicyDriftTrendRead:
    rows, next_cursor = await trend_telemetry.read_trend_events(
        db,
        org_id=int(user["org_id"]),
        event_type=trend_telemetry.GOVERNANCE_EVENT,
        limit=limit,
        cursor=cursor,
    )
    points: list[PolicyDriftTrendPointRead] = []
    for row in rows:
        payload = row.payload_json if isinstance(row.payload_json, dict) else {}
        try:
            max_drift = float(payload.get("max_drift_percent", 0.0) or 0.0)
        except (TypeError, ValueError):
            max_drift = 0.0
        try:
            signal_count = int(payload.get("signals", 0) or 0)
        except (TypeError, ValueError):
            signal_count = 0
        points.append(
            PolicyDriftTrendPointRead(
                timestamp=row.created_at,
                max_drift_percent=max_drift,
                signal_count=signal_count,
            )
        )
    return PolicyDriftTrendRead(points=points, next_cursor=next_cursor)
