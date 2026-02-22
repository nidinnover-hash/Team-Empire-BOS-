from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.schemas.intelligence import DecisionTraceRead, ExecutiveDiffRead, ExecutiveSummaryRead
from app.services import intelligence as intelligence_service

router = APIRouter(prefix="/intelligence", tags=["Intelligence"])


@router.get("/summary", response_model=ExecutiveSummaryRead)
async def executive_summary(
    window_days: int = Query(7, ge=3, le=90),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> ExecutiveSummaryRead:
    return await intelligence_service.build_executive_summary(
        db=db,
        organization_id=actor["org_id"],
        window_days=window_days,
    )


@router.get("/diff", response_model=ExecutiveDiffRead)
async def executive_diff(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> ExecutiveDiffRead:
    return await intelligence_service.build_change_since_yesterday(
        db=db,
        organization_id=actor["org_id"],
    )


@router.get("/traces", response_model=list[DecisionTraceRead])
async def list_traces(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list[DecisionTraceRead]:
    rows = await intelligence_service.list_decision_traces(
        db=db,
        organization_id=actor["org_id"],
        limit=limit,
    )
    traces: list[DecisionTraceRead] = []
    for row in rows:
        score = float(row.confidence_score or 0.0)
        if score >= 0.8:
            risk_tier = "low"
        elif score >= 0.55:
            risk_tier = "medium"
        else:
            risk_tier = "high"
        signals = row.signals_json if isinstance(row.signals_json, dict) else {}
        reasoning = [
            f"{k}: {v}" for k, v in signals.items() if k in {"drafted_plan_count", "drafted_email_count", "pending_approvals", "team_filter"}
        ]
        if not reasoning:
            reasoning = ["Trace captured from operational event history."]
        traces.append(
            DecisionTraceRead(
                id=row.id,
                organization_id=row.organization_id,
                trace_type=row.trace_type,
                title=row.title,
                summary=row.summary,
                confidence_score=score,
                risk_tier=risk_tier,
                reasoning=reasoning,
                signals_json=signals,
                actor_user_id=row.actor_user_id,
                daily_run_id=row.daily_run_id,
                source_event_id=row.source_event_id,
                created_at=row.created_at,
            )
        )
    return traces
