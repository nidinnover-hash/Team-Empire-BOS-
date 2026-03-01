from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_db
from app.core.rbac import require_roles
from app.logs.audit import record_action
from app.models.coaching_report import CoachingReport
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


# ---- AI Coaching Endpoints (Phase 3) ----


@router.post("/employee/{employee_id}/coaching", response_model=dict)
async def generate_employee_coaching(
    employee_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    from app.services import ai_coaching

    result = await ai_coaching.generate_employee_coaching(
        db, employee_id=employee_id, org_id=int(user["org_id"]),
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    await record_action(
        db,
        event_type="coaching_generated",
        actor_user_id=user["id"],
        organization_id=user["org_id"],
        entity_type="coaching_report",
        entity_id=result["report_id"],
        payload_json={"employee_id": employee_id},
    )
    return result


@router.post("/department/{department_id}/recommendations", response_model=dict)
async def generate_department_recommendations(
    department_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    from app.services import ai_coaching

    result = await ai_coaching.generate_department_recommendations(
        db, department_id=department_id, org_id=int(user["org_id"]),
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Department not found")
    await record_action(
        db,
        event_type="dept_recommendations_generated",
        actor_user_id=user["id"],
        organization_id=user["org_id"],
        entity_type="coaching_report",
        entity_id=result["report_id"],
        payload_json={"department_id": department_id},
    )
    return result


@router.post("/org/improvement-plan", response_model=dict)
async def generate_org_improvement_plan(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    from app.services import ai_coaching

    result = await ai_coaching.generate_org_improvement_plan(
        db, org_id=int(user["org_id"]),
    )
    await record_action(
        db,
        event_type="org_improvement_plan_generated",
        actor_user_id=user["id"],
        organization_id=user["org_id"],
        entity_type="coaching_report",
        entity_id=result["report_id"],
        payload_json={},
    )
    return result


# ---- Coaching Report Management ----


@router.get("/coaching", response_model=list[dict])
async def list_coaching_reports(
    report_type: str | None = Query(None),
    status: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> list[dict]:
    query = select(CoachingReport).where(
        CoachingReport.organization_id == int(user["org_id"]),
    )
    if report_type:
        query = query.where(CoachingReport.report_type == report_type)
    if status:
        query = query.where(CoachingReport.status == status)
    query = query.order_by(CoachingReport.created_at.desc()).offset(skip).limit(limit)
    rows = (await db.execute(query)).scalars().all()
    return [
        {
            "id": r.id, "report_type": r.report_type, "title": r.title,
            "summary": r.summary, "status": r.status,
            "employee_id": r.employee_id, "department_id": r.department_id,
            "recommendations": r.recommendations_json,
            "approved_by": r.approved_by,
            "approved_at": r.approved_at.isoformat() if r.approved_at else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.get("/coaching/{report_id}", response_model=dict)
async def get_coaching_report(
    report_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    row = (
        await db.execute(
            select(CoachingReport).where(
                CoachingReport.id == report_id,
                CoachingReport.organization_id == int(user["org_id"]),
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Coaching report not found")
    return {
        "id": row.id, "report_type": row.report_type, "title": row.title,
        "summary": row.summary, "status": row.status,
        "employee_id": row.employee_id, "department_id": row.department_id,
        "recommendations": row.recommendations_json,
        "approved_by": row.approved_by,
        "approved_at": row.approved_at.isoformat() if row.approved_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.patch("/coaching/{report_id}/approve", response_model=dict)
async def approve_coaching_report(
    report_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO")),
) -> dict:
    row = (
        await db.execute(
            select(CoachingReport).where(
                CoachingReport.id == report_id,
                CoachingReport.organization_id == int(user["org_id"]),
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Coaching report not found")
    row.status = "approved"
    row.approved_by = int(user["id"])
    row.approved_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(row)
    await record_action(
        db,
        event_type="coaching_report_approved",
        actor_user_id=user["id"],
        organization_id=user["org_id"],
        entity_type="coaching_report",
        entity_id=row.id,
        payload_json={"title": row.title},
    )
    return {"id": row.id, "status": row.status, "approved_by": row.approved_by}


@router.patch("/coaching/{report_id}/reject", response_model=dict)
async def reject_coaching_report(
    report_id: int,
    note: str | None = Query(None, max_length=500),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO")),
) -> dict:
    row = (
        await db.execute(
            select(CoachingReport).where(
                CoachingReport.id == report_id,
                CoachingReport.organization_id == int(user["org_id"]),
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Coaching report not found")
    row.status = "rejected"
    row.approved_by = int(user["id"])
    row.approved_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(row)
    await record_action(
        db,
        event_type="coaching_report_rejected",
        actor_user_id=user["id"],
        organization_id=user["org_id"],
        entity_type="coaching_report",
        entity_id=row.id,
        payload_json={"title": row.title, "note": note},
    )
    return {"id": row.id, "status": row.status, "rejected_by": row.approved_by}


# ---- Learning Feedback Endpoints (Phase 4) ----


@router.post("/outcomes", response_model=dict)
async def record_learning_outcome(
    coaching_report_id: int = Query(...),
    was_applied: bool = Query(...),
    outcome_score: float = Query(..., ge=0.0, le=1.0),
    notes: str | None = Query(None, max_length=2000),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    from app.services import learning_feedback

    result = await learning_feedback.record_outcome(
        db,
        org_id=int(user["org_id"]),
        coaching_report_id=coaching_report_id,
        was_applied=was_applied,
        outcome_score=outcome_score,
        notes=notes,
    )
    return result


@router.get("/learning-insights", response_model=dict)
async def get_learning_insights(
    days: int = Query(90, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    from app.services import learning_feedback

    return await learning_feedback.get_learning_insights(
        db, org_id=int(user["org_id"]), days=days,
    )
