from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_db
from app.core.rbac import require_roles
from app.logs.audit import record_action
from app.schemas.performance import (
    DepartmentOKRProgressRead,
    DepartmentPerformance,
    EmployeePerformance,
    OrgChartRead,
    OrgPerformance,
    PerformanceAlert,
    SkillMatrixRead,
    WorkloadBalanceRead,
)
from app.services import performance as perf_service

router = APIRouter(prefix="/performance", tags=["Performance"])


@router.post("/employee/{employee_id}/coaching", response_model=dict)
async def generate_employee_coaching_legacy(
    employee_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    """Backward-compatible coaching endpoint kept for older clients/tests."""
    from app.services import ai_coaching

    result = await ai_coaching.generate_employee_coaching(
        db, employee_id=employee_id, org_id=int(user["org_id"]),
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    return result


@router.get("/learning-insights", response_model=dict)
async def get_learning_insights_legacy(
    days: int = Query(90, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    """Backward-compatible route; canonical endpoint is /api/v1/coaching/insights."""
    from app.services import learning_feedback

    return await learning_feedback.get_learning_insights(
        db, org_id=int(user["org_id"]), days=days,
    )


@router.post("/outcomes", response_model=dict)
async def record_learning_outcome_legacy(
    coaching_report_id: int = Query(...),
    was_applied: bool = Query(...),
    outcome_score: float = Query(..., ge=0.0, le=1.0),
    notes: str | None = Query(None, max_length=2000),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    """Backward-compatible route; canonical endpoint is /api/v1/coaching/outcomes."""
    from app.services import learning_feedback

    return await learning_feedback.record_outcome(
        db,
        org_id=int(user["org_id"]),
        coaching_report_id=coaching_report_id,
        was_applied=was_applied,
        outcome_score=outcome_score,
        notes=notes,
    )


@router.get("/employee/{employee_id}", response_model=EmployeePerformance)
async def get_employee_performance(
    employee_id: int,
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> EmployeePerformance:
    result = await perf_service.get_employee_performance(
        db, employee_id=employee_id, org_id=int(user["org_id"]), days=days,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    return result


@router.get("/department/{department_id}", response_model=DepartmentPerformance)
async def get_department_performance(
    department_id: int,
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> DepartmentPerformance:
    result = await perf_service.get_department_performance(
        db, department_id=department_id, org_id=int(user["org_id"]), days=days,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Department not found")
    return result


@router.get("/org", response_model=OrgPerformance)
async def get_org_performance(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> OrgPerformance:
    return await perf_service.get_org_performance(
        db, org_id=int(user["org_id"]), days=days,
    )


@router.get("/top", response_model=list[EmployeePerformance])
async def get_top_performers(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list[EmployeePerformance]:
    return await perf_service.get_top_performers(
        db, org_id=int(user["org_id"]), days=days, limit=limit,
    )


@router.get("/alerts", response_model=list[PerformanceAlert])
async def get_performance_alerts(
    days: int = Query(30, ge=1, le=365),
    threshold: float = Query(0.3, ge=0.0, le=1.0),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list[PerformanceAlert]:
    return await perf_service.get_performance_alerts(
        db, org_id=int(user["org_id"]), days=days, threshold=threshold,
    )


@router.get("/org-chart", response_model=OrgChartRead)
async def get_org_chart(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> OrgChartRead:
    if not settings.FEATURE_OPS_INTEL or not settings.FEATURE_ORG_CHART_INTEL:
        raise HTTPException(status_code=404, detail="Feature disabled")
    return await perf_service.get_org_chart(
        db,
        org_id=int(user["org_id"]),
    )


@router.get("/workload-balance", response_model=WorkloadBalanceRead)
async def get_workload_balance(
    for_date: date | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> WorkloadBalanceRead:
    if not settings.FEATURE_OPS_INTEL or not settings.FEATURE_WORKLOAD_BALANCER:
        raise HTTPException(status_code=404, detail="Feature disabled")
    target_date = for_date or date.today()
    result = await perf_service.get_workload_balance(
        db,
        org_id=int(user["org_id"]),
        for_date=target_date,
    )
    await record_action(
        db,
        event_type="workload_balance_analyzed",
        actor_user_id=user["id"],
        organization_id=user["org_id"],
        entity_type="performance",
        entity_id=None,
        payload_json={
            "for_date": target_date.isoformat(),
            "overloaded_count": result.overloaded_count,
            "underloaded_count": result.underloaded_count,
        },
    )
    return result


@router.get("/skills-matrix", response_model=SkillMatrixRead)
async def get_skills_matrix(
    required_skills: list[str] = Query(default_factory=list),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> SkillMatrixRead:
    if not settings.FEATURE_OPS_INTEL or not settings.FEATURE_SKILL_MATRIX:
        raise HTTPException(status_code=404, detail="Feature disabled")
    return await perf_service.get_skill_matrix(
        db,
        org_id=int(user["org_id"]),
        required_skills=required_skills,
    )


@router.get("/department/{department_id}/okr-progress", response_model=DepartmentOKRProgressRead)
async def get_department_okr_progress(
    department_id: int,
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> DepartmentOKRProgressRead:
    if not settings.FEATURE_OPS_INTEL or not settings.FEATURE_DEPARTMENT_OKR_AUTOPROGRESS:
        raise HTTPException(status_code=404, detail="Feature disabled")
    end_date = to_date or datetime.now(UTC).date()
    start_date = from_date or (end_date - timedelta(days=6))
    result = await perf_service.get_department_okr_progress(
        db,
        org_id=int(user["org_id"]),
        department_id=department_id,
        from_date=start_date,
        to_date=end_date,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Department not found")
    await record_action(
        db,
        event_type="department_okr_progress_generated",
        actor_user_id=user["id"],
        organization_id=user["org_id"],
        entity_type="department",
        entity_id=department_id,
        payload_json={
            "from_date": start_date.isoformat(),
            "to_date": end_date.isoformat(),
            "overall_progress_percent": result.overall_progress_percent,
        },
    )
    return result
