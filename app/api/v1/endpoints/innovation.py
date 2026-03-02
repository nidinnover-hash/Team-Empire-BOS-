"""Innovation endpoints — sales coaching, cross-layer intelligence, experiments,
CTO strategic review, system health, layer trends, policy effectiveness, clone memory.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import (
    clone_memory,
    clone_sales_coach,
    cross_layer_intelligence,
    cto_strategic,
    experiment_tracker,
    layer_snapshots,
    policy_effectiveness,
    system_health,
)

router = APIRouter(tags=["innovation"])


# ── Sales Clone Coaching ──────────────────────────────────────────────


@router.post("/sales/interactions", response_model=dict)
async def record_sales_interaction(
    employee_id: int,
    interaction_type: str = Query("call"),
    outcome: str = Query("pending"),
    outcome_score: float = Query(0.5, ge=0.0, le=1.0),
    contact_id: int | None = Query(None),
    channel: str | None = Query(None),
    objection_encountered: str | None = Query(None),
    response_given: str | None = Query(None),
    context_notes: str | None = Query(None),
    loss_reason: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> dict:
    entry = await clone_sales_coach.record_interaction(
        db, int(user["org_id"]), employee_id, interaction_type,
        contact_id=contact_id, channel=channel,
        objection_encountered=objection_encountered,
        response_given=response_given, context_notes=context_notes,
        outcome=outcome, outcome_score=outcome_score, loss_reason=loss_reason,
    )
    return {"ok": True, "id": entry.id}


@router.get("/sales/interactions", response_model=dict)
async def list_sales_interactions(
    employee_id: int | None = Query(None),
    outcome: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> dict:
    items = await clone_sales_coach.list_interactions(
        db, int(user["org_id"]), employee_id=employee_id,
        outcome=outcome, skip=skip, limit=limit,
    )
    return {"items": [
        {
            "id": i.id, "employee_id": i.employee_id, "contact_id": i.contact_id,
            "interaction_type": i.interaction_type, "channel": i.channel,
            "objection_encountered": i.objection_encountered,
            "response_given": i.response_given, "outcome": i.outcome,
            "outcome_score": i.outcome_score, "loss_reason": i.loss_reason,
            "created_at": i.created_at.isoformat() if i.created_at else None,
        }
        for i in items
    ], "count": len(items)}


@router.get("/sales/loss-patterns", response_model=dict)
async def sales_loss_patterns(
    employee_id: int | None = Query(None),
    days: int = Query(90, ge=7, le=365),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> dict:
    return await clone_sales_coach.get_loss_patterns(
        db, int(user["org_id"]), employee_id=employee_id, days=days,
    )


@router.get("/sales/win-patterns", response_model=dict)
async def sales_win_patterns(
    employee_id: int | None = Query(None),
    days: int = Query(90, ge=7, le=365),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> dict:
    return await clone_sales_coach.get_win_patterns(
        db, int(user["org_id"]), employee_id=employee_id, days=days,
    )


@router.get("/sales/playbook", response_model=dict)
async def sales_objection_playbook(
    employee_id: int | None = Query(None),
    days: int = Query(90, ge=7, le=365),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    return await clone_sales_coach.generate_objection_playbook(
        db, int(user["org_id"]), employee_id=employee_id, days=days,
    )


@router.get("/sales/employee-stats/{employee_id}", response_model=dict)
async def sales_employee_stats(
    employee_id: int,
    days: int = Query(30, ge=7, le=365),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> dict:
    return await clone_sales_coach.get_employee_sales_stats(
        db, int(user["org_id"]), employee_id, days=days,
    )


# ── Cross-Layer Intelligence ─────────────────────────────────────────


@router.get("/intelligence/cross-layer", response_model=dict)
async def cross_layer_analysis(
    window_days: int = Query(30, ge=7, le=180),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    return await cross_layer_intelligence.analyze_cross_layer(
        db, int(user["org_id"]), window_days,
    )


# ── Layer Score Trends ────────────────────────────────────────────────


@router.post("/layers/snapshot", response_model=dict)
async def snapshot_layers(
    window_days: int = Query(30, ge=7, le=180),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    return await layer_snapshots.snapshot_all_layers(
        db, int(user["org_id"]), window_days,
    )


@router.get("/layers/trend/{layer_name}", response_model=dict)
async def layer_trend(
    layer_name: str,
    limit: int = Query(12, ge=2, le=52),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> dict:
    points = await layer_snapshots.get_layer_trend(
        db, int(user["org_id"]), layer_name, limit,
    )
    return {"layer": layer_name, "points": points}


@router.get("/layers/trends", response_model=dict)
async def all_layer_trends(
    limit: int = Query(12, ge=2, le=52),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> dict:
    return await layer_snapshots.get_all_layer_trends(
        db, int(user["org_id"]), limit,
    )


# ── Policy Effectiveness ─────────────────────────────────────────────


@router.get("/governance/policy-effectiveness", response_model=dict)
async def policy_effectiveness_report(
    weeks: int = Query(8, ge=2, le=52),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    return await policy_effectiveness.get_policy_effectiveness(
        db, int(user["org_id"]), weeks,
    )


@router.get("/governance/policy-effectiveness/{policy_id}/trend", response_model=dict)
async def policy_violation_trend(
    policy_id: int,
    weeks: int = Query(12, ge=2, le=52),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    points = await policy_effectiveness.get_violation_rate_trend(
        db, int(user["org_id"]), policy_id, weeks,
    )
    return {"policy_id": policy_id, "points": points}


# ── CTO Strategic Review ─────────────────────────────────────────────


@router.post("/brain/cto-strategic-review", response_model=dict)
async def cto_strategic_review(
    challenge: str = Query(""),
    window_days: int = Query(30, ge=7, le=180),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO")),
) -> dict:
    return await cto_strategic.run_strategic_review(
        db, int(user["org_id"]), challenge, window_days,
    )


# ── System Health ─────────────────────────────────────────────────────


@router.get("/system/health", response_model=dict)
async def system_health_summary(
    days: int = Query(7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    return await system_health.get_health_summary(
        db, int(user["org_id"]), days,
    )


@router.get("/system/health/events", response_model=dict)
async def system_health_events(
    category: str | None = Query(None),
    severity: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    events = await system_health.get_recent_events(
        db, int(user["org_id"]), category, severity, limit,
    )
    return {"events": events, "count": len(events)}


@router.get("/system/health/autopsy", response_model=dict)
async def system_health_autopsy(
    days: int = Query(7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    return await system_health.generate_autopsy(
        db, int(user["org_id"]), days,
    )


# ── Innovation Experiments ────────────────────────────────────────────


@router.post("/experiments", response_model=dict)
async def create_experiment(
    title: str = Query(...),
    hypothesis: str = Query(...),
    success_metric: str = Query(...),
    area: str = Query("general"),
    baseline_value: float | None = Query(None),
    target_value: float | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    exp = await experiment_tracker.create_experiment(
        db, int(user["org_id"]), title, hypothesis, success_metric,
        area=area, baseline_value=baseline_value, target_value=target_value,
        created_by=int(user["id"]),
    )
    return {"ok": True, "id": exp.id, "status": exp.status}


@router.get("/experiments", response_model=dict)
async def list_experiments(
    status: str | None = Query(None),
    area: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> dict:
    items = await experiment_tracker.list_experiments(
        db, int(user["org_id"]), status=status, area=area, skip=skip, limit=limit,
    )
    return {"items": [
        {
            "id": e.id, "title": e.title, "hypothesis": e.hypothesis,
            "success_metric": e.success_metric, "area": e.area,
            "status": e.status, "outcome": e.outcome,
            "baseline_value": e.baseline_value, "target_value": e.target_value,
            "actual_value": e.actual_value,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in items
    ], "count": len(items)}


@router.post("/experiments/{experiment_id}/start", response_model=dict)
async def start_experiment(
    experiment_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    exp = await experiment_tracker.start_experiment(
        db, int(user["org_id"]), experiment_id,
    )
    if not exp:
        return {"ok": False, "error": "Experiment not found"}
    return {"ok": True, "id": exp.id, "status": exp.status}


@router.post("/experiments/{experiment_id}/complete", response_model=dict)
async def complete_experiment(
    experiment_id: int,
    actual_value: float = Query(...),
    outcome: str = Query("inconclusive"),
    outcome_notes: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    exp = await experiment_tracker.complete_experiment(
        db, int(user["org_id"]), experiment_id,
        actual_value=actual_value, outcome=outcome, outcome_notes=outcome_notes,
    )
    if not exp:
        return {"ok": False, "error": "Experiment not found"}
    return {"ok": True, "id": exp.id, "status": exp.status, "outcome": exp.outcome}


@router.get("/experiments/velocity", response_model=dict)
async def innovation_velocity(
    days: int = Query(90, ge=7, le=365),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> dict:
    return await experiment_tracker.get_innovation_velocity(
        db, int(user["org_id"]), days,
    )


# ── Clone Memory ─────────────────────────────────────────────────────


@router.post("/clone/memory", response_model=dict)
async def store_clone_memory(
    employee_id: int,
    situation: str = Query(...),
    action_taken: str = Query(...),
    outcome: str = Query("success"),
    outcome_detail: str | None = Query(None),
    category: str = Query("general"),
    tags: str | None = Query(None),
    confidence: float = Query(0.7, ge=0.0, le=1.0),
    source_type: str | None = Query(None),
    source_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> dict:
    entry = await clone_memory.store_memory(
        db, int(user["org_id"]), employee_id, situation, action_taken, outcome,
        outcome_detail=outcome_detail, category=category, tags=tags,
        confidence=confidence, source_type=source_type, source_id=source_id,
    )
    return {"ok": True, "id": entry.id}


@router.get("/clone/memory/search", response_model=dict)
async def search_clone_memory(
    employee_id: int,
    query: str = Query(..., min_length=2),
    category: str | None = Query(None),
    outcome_filter: str | None = Query(None),
    limit: int = Query(5, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> dict:
    memories = await clone_memory.retrieve_similar(
        db, int(user["org_id"]), employee_id, query,
        category=category, outcome_filter=outcome_filter, limit=limit,
    )
    return {"items": [
        {
            "id": m.id, "situation": m.situation, "action_taken": m.action_taken,
            "outcome": m.outcome, "category": m.category,
            "confidence": round(m.confidence, 3),
            "reinforcement_count": m.reinforcement_count,
        }
        for m in memories
    ], "count": len(memories)}


@router.post("/clone/memory/{memory_id}/reinforce", response_model=dict)
async def reinforce_clone_memory(
    memory_id: int,
    boost: float = Query(0.05, ge=0.01, le=0.2),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> dict:
    entry = await clone_memory.reinforce_memory(
        db, int(user["org_id"]), memory_id, confidence_boost=boost,
    )
    if not entry:
        return {"ok": False, "error": "Memory not found"}
    return {"ok": True, "confidence": round(entry.confidence, 3), "reinforcements": entry.reinforcement_count}


@router.get("/clone/memory/stats", response_model=dict)
async def clone_memory_stats(
    employee_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> dict:
    return await clone_memory.get_memory_stats(
        db, int(user["org_id"]), employee_id,
    )
