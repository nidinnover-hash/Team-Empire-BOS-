"""Cross-org governance engine.

Manages policies, evaluates compliance, tracks violations,
and calculates progressive automation levels.
All final decisions go through CEO (Nidin Nover).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee
from app.models.employee_work_pattern import EmployeeWorkPattern
from app.models.governance import GovernancePolicy, GovernanceViolation
from app.models.learning_outcome import LearningOutcome
from app.schemas.governance import (
    AutomationLevel,
    ComplianceSummary,
    GovernancePolicyCreate,
    GovernancePolicyUpdate,
)


async def create_policy(
    db: AsyncSession,
    org_id: int,
    data: GovernancePolicyCreate,
    created_by: int | None = None,
) -> GovernancePolicy:
    policy = GovernancePolicy(
        organization_id=org_id,
        name=data.name,
        description=data.description,
        policy_type=data.policy_type,
        rules_json=data.rules_json,
        requires_ceo_approval=data.requires_ceo_approval,
        created_by=created_by,
    )
    db.add(policy)
    await db.commit()
    await db.refresh(policy)
    return policy


async def list_policies(
    db: AsyncSession,
    org_id: int,
    active_only: bool = True,
    skip: int = 0,
    limit: int = 50,
) -> list[GovernancePolicy]:
    query = select(GovernancePolicy).where(GovernancePolicy.organization_id == org_id)
    if active_only:
        query = query.where(GovernancePolicy.is_active is True)
    query = query.order_by(GovernancePolicy.name).offset(skip).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_policy(
    db: AsyncSession,
    org_id: int,
    policy_id: int,
) -> GovernancePolicy | None:
    result = await db.execute(
        select(GovernancePolicy).where(
            GovernancePolicy.id == policy_id,
            GovernancePolicy.organization_id == org_id,
        )
    )
    return result.scalar_one_or_none()


async def update_policy(
    db: AsyncSession,
    org_id: int,
    policy_id: int,
    data: GovernancePolicyUpdate,
) -> GovernancePolicy | None:
    policy = await get_policy(db, org_id, policy_id)
    if policy is None:
        return None
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(policy, field, value)
    await db.commit()
    await db.refresh(policy)
    return policy


async def evaluate_compliance(
    db: AsyncSession,
    org_id: int,
    cutoff_days: int = 7,
) -> list[dict[str, Any]]:
    """Check all employees against active policies using bulk queries."""
    policies = await list_policies(db, org_id, active_only=True)
    cutoff = (datetime.now(UTC) - timedelta(days=cutoff_days)).date()

    # Bulk aggregate all employees in one query
    bulk_agg = (
        await db.execute(
            select(
                Employee.id,
                Employee.name,
                func.avg(EmployeeWorkPattern.hours_logged),
                func.avg(EmployeeWorkPattern.tasks_completed),
                func.avg(EmployeeWorkPattern.focus_minutes),
                func.avg(EmployeeWorkPattern.active_minutes),
            )
            .outerjoin(
                EmployeeWorkPattern,
                (EmployeeWorkPattern.employee_id == Employee.id)
                & (EmployeeWorkPattern.organization_id == org_id)
                & (EmployeeWorkPattern.work_date >= cutoff),
            )
            .where(
                Employee.organization_id == org_id,
                Employee.is_active is True,
            )
            .group_by(Employee.id, Employee.name)
        )
    ).all()

    # Load existing open violations for deduplication
    existing_open = (
        await db.execute(
            select(
                GovernanceViolation.policy_id,
                GovernanceViolation.employee_id,
                GovernanceViolation.violation_type,
            ).where(
                GovernanceViolation.organization_id == org_id,
                GovernanceViolation.status == "open",
            )
        )
    ).all()
    open_set = {(r[0], r[1], r[2]) for r in existing_open}

    violations_found: list[dict[str, Any]] = []

    for policy in policies:
        rules = policy.rules_json or {}
        min_hours = rules.get("min_hours_per_day")
        min_tasks = rules.get("min_tasks_per_day")
        min_focus_ratio = rules.get("min_focus_ratio")

        if not any([min_hours, min_tasks, min_focus_ratio]):
            continue

        for emp_id, emp_name, avg_h, avg_t, avg_f, avg_a in bulk_agg:
            avg_h = float(avg_h or 0)
            avg_t = float(avg_t or 0)
            avg_f = float(avg_f or 0)
            avg_a = float(avg_a or 1)
            focus_ratio = avg_f / avg_a if avg_a > 0 else 0

            violations_for_emp: list[tuple[str, str]] = []
            if min_hours and avg_h < float(min_hours):
                violations_for_emp.append(("hours_below_minimum", f"avg hours {avg_h:.1f} < required {min_hours}"))
            if min_tasks and avg_t < float(min_tasks):
                violations_for_emp.append(("tasks_below_minimum", f"avg tasks {avg_t:.1f} < required {min_tasks}"))
            if min_focus_ratio and focus_ratio < float(min_focus_ratio):
                violations_for_emp.append(("focus_below_minimum", f"focus ratio {focus_ratio:.2f} < required {min_focus_ratio}"))

            if violations_for_emp:
                reasons = [r for _, r in violations_for_emp]
                v_types = [vt for vt, _ in violations_for_emp]
                primary_type = v_types[0] if len(v_types) == 1 else "performance_below_threshold"

                if (policy.id, emp_id, primary_type) in open_set:
                    continue  # Skip duplicate

                violation = GovernanceViolation(
                    organization_id=org_id,
                    policy_id=policy.id,
                    employee_id=emp_id,
                    violation_type=primary_type,
                    details_json={
                        "policy_name": policy.name,
                        "employee_name": emp_name,
                        "reasons": reasons,
                        "violation_types": v_types,
                        "avg_hours": round(avg_h, 2),
                        "avg_tasks": round(avg_t, 2),
                        "focus_ratio": round(focus_ratio, 4),
                    },
                )
                db.add(violation)
                open_set.add((policy.id, emp_id, primary_type))
                violations_found.append({
                    "employee_id": emp_id,
                    "employee_name": emp_name,
                    "policy_name": policy.name,
                    "reasons": reasons,
                })

    if violations_found:
        await db.commit()
    return violations_found


async def check_employee_compliance(
    db: AsyncSession,
    employee_id: int,
    org_id: int,
) -> dict[str, Any]:
    """Check a single employee against all active policies."""
    violations = (
        await db.execute(
            select(GovernanceViolation).where(
                GovernanceViolation.employee_id == employee_id,
                GovernanceViolation.organization_id == org_id,
                GovernanceViolation.status == "open",
            ).order_by(GovernanceViolation.created_at.desc())
        )
    ).scalars().all()

    return {
        "employee_id": employee_id,
        "open_violations": len(violations),
        "is_compliant": len(violations) == 0,
        "violations": [
            {
                "id": v.id,
                "policy_id": v.policy_id,
                "violation_type": v.violation_type,
                "details": v.details_json,
                "created_at": v.created_at.isoformat() if v.created_at else None,
            }
            for v in violations
        ],
    }


async def list_violations(
    db: AsyncSession,
    org_id: int,
    status: str | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list[GovernanceViolation]:
    query = select(GovernanceViolation).where(GovernanceViolation.organization_id == org_id)
    if status:
        query = query.where(GovernanceViolation.status == status)
    query = query.order_by(GovernanceViolation.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


async def resolve_violation(
    db: AsyncSession,
    org_id: int,
    violation_id: int,
    resolved_by: int,
    status: str = "resolved",
) -> GovernanceViolation | None:
    result = await db.execute(
        select(GovernanceViolation).where(
            GovernanceViolation.id == violation_id,
            GovernanceViolation.organization_id == org_id,
        )
    )
    violation = result.scalar_one_or_none()
    if violation is None:
        return None
    violation.status = status
    violation.resolved_by = resolved_by
    violation.resolved_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(violation)
    return violation


async def get_governance_dashboard(
    db: AsyncSession,
    org_id: int,
) -> ComplianceSummary:
    total_policies = int(
        (
            await db.execute(
                select(func.count(GovernancePolicy.id)).where(
                    GovernancePolicy.organization_id == org_id
                )
            )
        ).scalar_one() or 0
    )
    active_policies = int(
        (
            await db.execute(
                select(func.count(GovernancePolicy.id)).where(
                    GovernancePolicy.organization_id == org_id,
                    GovernancePolicy.is_active is True,
                )
            )
        ).scalar_one() or 0
    )
    total_violations = int(
        (
            await db.execute(
                select(func.count(GovernanceViolation.id)).where(
                    GovernanceViolation.organization_id == org_id
                )
            )
        ).scalar_one() or 0
    )
    open_violations = int(
        (
            await db.execute(
                select(func.count(GovernanceViolation.id)).where(
                    GovernanceViolation.organization_id == org_id,
                    GovernanceViolation.status == "open",
                )
            )
        ).scalar_one() or 0
    )
    resolved = total_violations - open_violations
    compliance_rate = round(resolved / max(total_violations, 1), 4)

    return ComplianceSummary(
        total_policies=total_policies,
        active_policies=active_policies,
        total_violations=total_violations,
        open_violations=open_violations,
        resolved_violations=resolved,
        compliance_rate=compliance_rate,
    )


async def detect_policy_drift(
    db: AsyncSession,
    org_id: int,
    window_days: int = 14,
) -> dict[str, Any]:
    """Detect drift where recent behavior degrades vs baseline for policy-governed metrics."""
    days = max(14, window_days)
    recent_days = max(7, days // 2)
    now_date = datetime.now(UTC).date()
    recent_start = now_date - timedelta(days=recent_days - 1)
    baseline_end = recent_start - timedelta(days=1)
    baseline_start = baseline_end - timedelta(days=recent_days - 1)

    def _drift_percent(baseline: float, current: float) -> float:
        if baseline <= 0:
            return 0.0
        return round(((baseline - current) / baseline) * 100.0, 2)

    async def _window_metrics(start: date, end: date) -> dict[str, float]:
        row = (
            await db.execute(
                select(
                    func.avg(EmployeeWorkPattern.hours_logged),
                    func.avg(EmployeeWorkPattern.tasks_completed),
                    func.sum(EmployeeWorkPattern.focus_minutes),
                    func.sum(EmployeeWorkPattern.active_minutes),
                ).where(
                    EmployeeWorkPattern.organization_id == org_id,
                    EmployeeWorkPattern.work_date >= start,
                    EmployeeWorkPattern.work_date <= end,
                )
            )
        ).one()
        avg_hours = float(row[0] or 0.0)
        avg_tasks = float(row[1] or 0.0)
        focus = float(row[2] or 0.0)
        active = float(row[3] or 0.0)
        return {
            "avg_hours": round(avg_hours, 4),
            "avg_tasks": round(avg_tasks, 4),
            "focus_ratio": round((focus / active), 4) if active > 0 else 0.0,
        }

    baseline = await _window_metrics(baseline_start, baseline_end)
    current = await _window_metrics(recent_start, now_date)
    policies = await list_policies(db, org_id=org_id, active_only=True, limit=200)

    violation_rows = (
        await db.execute(
            select(
                GovernanceViolation.policy_id,
                func.count(GovernanceViolation.id),
            ).where(
                GovernanceViolation.organization_id == org_id,
                GovernanceViolation.status == "open",
            ).group_by(GovernanceViolation.policy_id)
        )
    ).all()
    open_by_policy = {int(policy_id): int(count) for policy_id, count in violation_rows}

    signals: list[dict[str, Any]] = []
    for policy in policies:
        rules = policy.rules_json or {}
        metrics_to_check = [
            ("avg_hours", rules.get("min_hours_per_day")),
            ("avg_tasks", rules.get("min_tasks_per_day")),
            ("focus_ratio", rules.get("min_focus_ratio")),
        ]
        for metric_key, threshold_raw in metrics_to_check:
            if threshold_raw is None:
                continue
            threshold = float(threshold_raw)
            base_v = float(baseline.get(metric_key, 0.0))
            curr_v = float(current.get(metric_key, 0.0))
            drift = _drift_percent(base_v, curr_v)
            below_threshold = curr_v < threshold
            if not below_threshold and drift < 10.0:
                continue

            severity = "low"
            if below_threshold and drift >= 20.0:
                severity = "high"
            elif below_threshold or drift >= 15.0:
                severity = "medium"

            recommendation = (
                f"Policy '{policy.name}' shows drift on {metric_key}. "
                "Run manager review, rebalance workload, and re-check in 7 days."
            )
            signals.append(
                {
                    "policy_id": int(policy.id),
                    "policy_name": policy.name,
                    "metric": metric_key,
                    "baseline": round(base_v, 4),
                    "current": round(curr_v, 4),
                    "threshold": threshold,
                    "drift_percent": drift,
                    "below_threshold": below_threshold,
                    "severity": severity,
                    "open_violation_count": open_by_policy.get(int(policy.id), 0),
                    "recommendation": recommendation,
                }
            )

    status = "stable"
    if any(item["severity"] == "high" for item in signals):
        status = "critical"
    elif signals:
        status = "warning"

    return {
        "generated_at": datetime.now(UTC),
        "window_days": days,
        "status": status,
        "signals": sorted(signals, key=lambda item: (item["severity"], item["drift_percent"]), reverse=True),
    }


async def calculate_automation_level(
    db: AsyncSession,
    org_id: int,
) -> AutomationLevel:
    """Calculate progressive automation level.

    Starts at 5% automation / 95% human.
    Increases based on data quality, recommendation effectiveness, and compliance.
    """
    # Get recommendation stats
    from app.models.coaching_report import CoachingReport

    cutoff = datetime.now(UTC) - timedelta(days=90)

    total_recs = int(
        (
            await db.execute(
                select(func.count(CoachingReport.id)).where(
                    CoachingReport.organization_id == org_id,
                    CoachingReport.created_at >= cutoff,
                )
            )
        ).scalar_one() or 0
    )
    approved_recs = int(
        (
            await db.execute(
                select(func.count(CoachingReport.id)).where(
                    CoachingReport.organization_id == org_id,
                    CoachingReport.status == "approved",
                    CoachingReport.created_at >= cutoff,
                )
            )
        ).scalar_one() or 0
    )

    # Get outcome effectiveness
    outcomes_applied = int(
        (
            await db.execute(
                select(func.count(LearningOutcome.id)).where(
                    LearningOutcome.organization_id == org_id,
                    LearningOutcome.was_applied is True,
                    LearningOutcome.created_at >= cutoff,
                )
            )
        ).scalar_one() or 0
    )
    avg_outcome = (
        await db.execute(
            select(func.avg(LearningOutcome.outcome_score)).where(
                LearningOutcome.organization_id == org_id,
                LearningOutcome.was_applied is True,
                LearningOutcome.created_at >= cutoff,
            )
        )
    ).scalar_one()
    data_confidence = float(avg_outcome or 0.0)

    # Compliance rate
    dashboard = await get_governance_dashboard(db, org_id)

    # Work pattern data volume
    work_data_count = int(
        (
            await db.execute(
                select(func.count(EmployeeWorkPattern.id)).where(
                    EmployeeWorkPattern.organization_id == org_id,
                )
            )
        ).scalar_one() or 0
    )

    # Calculate automation level (starts at 0.05, max 0.95)
    # Factors: data volume, recommendation effectiveness, compliance
    data_factor = min(work_data_count / 1000.0, 1.0)  # normalise to 1000 data points
    rec_factor = approved_recs / max(total_recs, 1) if total_recs > 0 else 0.0
    outcome_factor = data_confidence
    compliance_factor = dashboard.compliance_rate

    raw_level = 0.05 + (
        data_factor * 0.25
        + rec_factor * 0.25
        + outcome_factor * 0.25
        + compliance_factor * 0.20
    ) * 0.90  # scale to max 0.95

    current_level = round(min(max(raw_level, 0.05), 0.95), 4)
    suggested_next = round(min(current_level + 0.05, 0.95), 4)

    reasoning_parts: list[str] = []
    if data_factor < 0.3:
        reasoning_parts.append("Insufficient work pattern data for higher automation")
    if rec_factor < 0.3:
        reasoning_parts.append("Low recommendation approval rate — more CEO validation needed")
    if outcome_factor < 0.5:
        reasoning_parts.append("Applied recommendations haven't shown strong results yet")
    if compliance_factor < 0.7:
        reasoning_parts.append("Compliance rate is below acceptable threshold")
    if not reasoning_parts:
        reasoning_parts.append("System performance metrics support current automation level")

    return AutomationLevel(
        current_level=current_level,
        human_control=round(1.0 - current_level, 4),
        data_confidence=round(data_confidence, 4),
        recommendations_applied=outcomes_applied,
        recommendations_total=total_recs,
        policy_compliance_rate=dashboard.compliance_rate,
        suggested_next_level=suggested_next,
        reasoning="; ".join(reasoning_parts),
    )
