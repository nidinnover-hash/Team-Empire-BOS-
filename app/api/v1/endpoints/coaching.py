"""Dedicated coaching endpoint — AI-generated coaching reports with CEO approval flow."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.logs.audit import record_action
from app.models.coaching_report import CoachingReport

router = APIRouter(prefix="/coaching", tags=["Coaching"])

# Max number of pending (unreviewed) AI coaching reports per org at any time.
# Prevents unbounded AI cost from rapid-fire generation before reports are reviewed.
_MAX_PENDING_REPORTS = 10


async def _guard_pending_limit(db: AsyncSession, org_id: int) -> None:
    """Raise 429 if the org already has too many pending coaching reports."""
    count: int = (
        await db.execute(
            select(func.count(CoachingReport.id)).where(
                CoachingReport.organization_id == org_id,
                CoachingReport.status == "pending",
            )
        )
    ).scalar_one()
    if count >= _MAX_PENDING_REPORTS:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Too many pending coaching reports ({count}/{_MAX_PENDING_REPORTS}). "
                "Approve or reject existing reports before generating new ones."
            ),
        )


# ── Report Generation ────────────────────────────────────────────────────────


@router.post("/employee/{employee_id}", response_model=dict)
async def generate_employee_coaching(
    employee_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    """Generate an AI coaching report for an employee (status=pending, requires approval)."""
    await _guard_pending_limit(db, int(user["org_id"]))
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


@router.post("/department/{department_id}", response_model=dict)
async def generate_department_coaching(
    department_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    """Generate AI recommendations for a department."""
    await _guard_pending_limit(db, int(user["org_id"]))
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


@router.post("/org", response_model=dict)
async def generate_org_improvement_plan(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    """Generate a strategic improvement plan for the whole organisation."""
    await _guard_pending_limit(db, int(user["org_id"]))
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


# ── Report Management ────────────────────────────────────────────────────────


@router.get("/insights", response_model=dict)
async def get_learning_insights(
    days: int = Query(90, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    from app.services import learning_feedback

    return await learning_feedback.get_learning_insights(
        db, org_id=int(user["org_id"]), days=days,
    )


@router.get("", response_model=list[dict])
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
    return [_serialize(r) for r in rows]


@router.get("/{report_id}", response_model=dict)
async def get_coaching_report(
    report_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    row = await _get_or_404(db, report_id, int(user["org_id"]))
    return _serialize(row)


@router.patch("/{report_id}/approve", response_model=dict)
async def approve_coaching_report(
    report_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO")),
) -> dict:
    row = await _get_or_404(db, report_id, int(user["org_id"]))
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


@router.patch("/{report_id}/reject", response_model=dict)
async def reject_coaching_report(
    report_id: int,
    note: str | None = Query(None, max_length=500),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO")),
) -> dict:
    row = await _get_or_404(db, report_id, int(user["org_id"]))
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


# ── Learning Feedback ────────────────────────────────────────────────────────


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

    return await learning_feedback.record_outcome(
        db,
        org_id=int(user["org_id"]),
        coaching_report_id=coaching_report_id,
        was_applied=was_applied,
        outcome_score=outcome_score,
        notes=notes,
    )


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _get_or_404(db: AsyncSession, report_id: int, org_id: int) -> CoachingReport:
    row = (
        await db.execute(
            select(CoachingReport).where(
                CoachingReport.id == report_id,
                CoachingReport.organization_id == org_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Coaching report not found")
    return row


def _serialize(r: CoachingReport) -> dict:
    return {
        "id": r.id,
        "report_type": r.report_type,
        "title": r.title,
        "summary": r.summary,
        "status": r.status,
        "employee_id": r.employee_id,
        "department_id": r.department_id,
        "recommendations": r.recommendations_json,
        "approved_by": r.approved_by,
        "approved_at": r.approved_at.isoformat() if r.approved_at else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }
