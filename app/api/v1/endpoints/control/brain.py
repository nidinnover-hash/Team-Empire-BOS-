"""Brain training, self-learning, limitations analysis, and scenario simulation."""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.core.request_context import get_current_request_id
from app.engines.brain.context import build_brain_context
from app.engines.brain.router import call_ai
from app.logs.audit import record_action
from app.schemas.control import (
    BrainTrainRead,
    BrainTrainRequest,
    CloneLimitationRead,
    CloneSelfDevelopRead,
    CloneSelfDevelopRequest,
    ScenarioSimulationRead,
    ScenarioSimulationRequest,
)
from app.services import (
    clone_brain,
    clone_control,
    metrics_service,
    self_learning,
    signal_ingestion,
)

from ._shared import _append_limitation, _to_float, _to_int

router = APIRouter()


@router.post("/brain/train-data-driven", response_model=BrainTrainRead)
async def brain_train_data_driven(
    payload: BrainTrainRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> BrainTrainRead:
    org_id = int(actor["org_id"])
    data_collection: dict[str, Any] = {}
    for name, fn in [
        ("clickup", signal_ingestion.ingest_clickup_signals),
        ("github", signal_ingestion.ingest_github_signals),
        ("github_cicd", signal_ingestion.ingest_github_cicd_signals),
        ("gmail", signal_ingestion.ingest_gmail_signals),
    ]:
        try:
            data_collection[name] = await fn(db, org_id)
        except (RuntimeError, ValueError, TypeError, SQLAlchemyError, TimeoutError, ConnectionError, OSError) as exc:
            data_collection[name] = {"ok": False, "error": type(exc).__name__}

    metrics: dict[str, Any]
    try:
        metrics_result = await metrics_service.compute_weekly_metrics(db, org_id, weeks=payload.weeks)
        metrics = metrics_result if isinstance(metrics_result, dict) else {"ok": True}
    except (RuntimeError, ValueError, TypeError, SQLAlchemyError, TimeoutError, ConnectionError, OSError) as exc:
        metrics = {"ok": False, "error": type(exc).__name__}

    today = datetime.now(UTC).date()
    week_start = today - timedelta(days=today.weekday())
    clone_training = await clone_brain.train_weekly_clone_scores(
        db,
        organization_id=org_id,
        week_start_date=week_start,
    )
    clone_summary = await clone_brain.clone_org_summary(
        db,
        organization_id=org_id,
        week_start_date=week_start,
    )
    dispatch = await clone_brain.build_dispatch_plan(
        db,
        organization_id=org_id,
        challenge=payload.challenge,
        week_start_date=week_start,
        top_n=5,
    )
    data_quality = await clone_control.data_quality_snapshot(db, organization_id=org_id)

    avg_score_raw = clone_summary.get("avg_score", 0.0)
    avg_score = float(avg_score_raw) if isinstance(avg_score_raw, int | float) else 0.0
    missing_identity_raw = data_quality.get("missing_identity_count", 0)
    missing_identity_count = int(missing_identity_raw) if isinstance(missing_identity_raw, int) else 0
    ceo_brain = {
        "challenge": payload.challenge,
        "strict_data_driven_mode": True,
        "avg_clone_score": avg_score,
        "dispatch_top_owners": [item.get("employee_name") for item in dispatch[:3]],
        "training_priorities": [
            "Close missing identity maps before expanding autonomous workflows."
            if missing_identity_count > 0
            else "Maintain identity map coverage across all active employees.",
            "Coach low-readiness clones with weekly measurable drills.",
            "Review metrics weekly and only scale strategies with proven outcomes.",
        ],
        "confidence": max(0.0, min(1.0, round((avg_score / 100.0) + 0.15, 2))),
    }

    return BrainTrainRead(
        ok=True,
        mode="suggest_only",
        data_collection=data_collection,
        metrics=metrics,
        clone_training={
            **clone_training,
            "summary": clone_summary,
            "dispatch": dispatch,
        },
        ceo_brain=ceo_brain,
    )


@router.post("/brain/self-learning-train", response_model=dict)
async def brain_self_learning_train(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    org_id = int(actor["org_id"])
    now = datetime.now(UTC)
    week_start = now.date() - timedelta(days=now.date().weekday())
    claimed, run_row = await self_learning.claim_weekly_run(
        db,
        organization_id=org_id,
        week_start_date=week_start,
        requested_by=int(actor["id"]),
    )
    if not claimed:
        return {
            "ok": True,
            "skipped": True,
            "reason": "already_trained_this_week",
            "week_start_date": week_start.isoformat(),
        }
    try:
        result = await self_learning.train_weekly_intelligence(
            db,
            organization_id=org_id,
        )
        await self_learning.complete_weekly_run(
            db,
            run_id=int(run_row.id),
            status="completed",
            details={"summary": result},
        )
        await record_action(
            db=db,
            event_type="self_learning_trained",
            actor_user_id=int(actor["id"]),
            organization_id=org_id,
            entity_type="control",
            entity_id=None,
            payload_json={
                "week_start_date": result.get("week_start_date"),
                "policy_drafts_created": result.get("policy_drafts_created", 0),
            },
        )
        return {"ok": True, **result}
    except (RuntimeError, ValueError, TypeError, SQLAlchemyError, TimeoutError, ConnectionError, OSError) as exc:
        await self_learning.complete_weekly_run(
            db,
            run_id=int(run_row.id),
            status="failed",
            details={"error": type(exc).__name__},
        )
        raise


@router.post("/brain/limitations-claude", response_model=CloneSelfDevelopRead)
async def brain_limitations_claude(
    payload: CloneSelfDevelopRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> CloneSelfDevelopRead:
    org_id = int(actor["org_id"])
    week_start = payload.week_start_date.date() if payload.week_start_date else None
    summary = await clone_brain.clone_org_summary(
        db,
        organization_id=org_id,
        week_start_date=week_start,
    )
    scores = await clone_brain.list_clone_scores(
        db,
        organization_id=org_id,
        week_start_date=week_start,
    )
    data_quality = await clone_control.data_quality_snapshot(db, organization_id=org_id)
    sla = await clone_control.manager_sla_snapshot(db, organization_id=org_id)

    limitations: list[CloneLimitationRead] = []
    avg_score = _to_float(summary.get("avg_score", 0.0), 0.0)
    if _to_int(summary.get("count", 0), 0) == 0:
        _append_limitation(
            limitations,
            name="no_clone_scores",
            severity="critical",
            impact="No measurable baseline for autonomous delegation quality.",
            evidence="No clone performance rows found for selected window.",
        )
    if avg_score < 55.0:
        _append_limitation(
            limitations,
            name="low_readiness_average",
            severity="high",
            impact="Autonomous decisions likely need heavy human correction.",
            evidence=f"Average clone score is {avg_score:.2f} (<55).",
        )
    needs_support = _to_int(summary.get("needs_support", 0), 0)
    if needs_support > 0:
        _append_limitation(
            limitations,
            name="high_needs_support_population",
            severity="high",
            impact="Execution quality risk concentrated in low-readiness clones.",
            evidence=f"{needs_support} clones in needs_support bucket.",
        )
    missing_identity = _to_int(data_quality.get("missing_identity_count", 0), 0)
    if missing_identity > 0:
        _append_limitation(
            limitations,
            name="identity_mapping_gaps",
            severity="high",
            impact="Signals cannot be attributed reliably to employee clones.",
            evidence=f"{missing_identity} active employees missing identity mapping.",
        )
    stale_metrics = _to_int(data_quality.get("stale_metrics_count", 0), 0)
    if stale_metrics > 0:
        _append_limitation(
            limitations,
            name="stale_weekly_metrics",
            severity="medium",
            impact="Model is training on incomplete or outdated performance telemetry.",
            evidence=f"{stale_metrics} employees missing current-week metrics.",
        )
    duplicate_conflicts = _to_int(data_quality.get("duplicate_identity_conflicts", 0), 0)
    if duplicate_conflicts > 0:
        _append_limitation(
            limitations,
            name="duplicate_identity_conflicts",
            severity="medium",
            impact="Ownership ambiguity can distort training feedback loops.",
            evidence=f"{duplicate_conflicts} duplicate work-email identity conflicts.",
        )
    pending_breaches = _to_int(sla.get("pending_approvals_breached", 0), 0)
    if pending_breaches > 0:
        _append_limitation(
            limitations,
            name="approval_sla_breaches",
            severity="medium",
            impact="Decision latency blocks clone learning and execution throughput.",
            evidence=f"{pending_breaches} pending approvals beyond SLA.",
        )
    if not limitations:
        _append_limitation(
            limitations,
            name="no_critical_limitations_detected",
            severity="low",
            impact="System appears stable; focus on incremental improvement.",
            evidence="No high-risk gaps detected in current diagnostics.",
        )

    diagnostics = {
        "week_start_date": week_start.isoformat() if week_start else None,
        "summary": summary,
        "score_count": len(scores),
        "data_quality": data_quality,
        "manager_sla": sla,
        "challenge": payload.challenge,
    }
    brain_context = await build_brain_context(
        db,
        organization_id=org_id,
        actor_user_id=int(actor["id"]),
        actor_role=str(actor["role"]),
        request_purpose=str(actor.get("purpose") or "professional"),
    )

    claude_plan = await call_ai(
        system_prompt=(
            "You are Claude acting as a clone capability architect. "
            "Given diagnostics and limitations, produce a practical self-development plan. "
            "Output plain text with sections: 'Top Limits', '7-Day Plan', '30-Day Plan', "
            "'Guardrails', and 'Success Metrics'. Keep it operational and measurable."
        ),
        user_message=json.dumps(
            {
                "challenge": payload.challenge,
                "diagnostics": diagnostics,
                "limitations": [item.model_dump() for item in limitations],
            },
            ensure_ascii=True,
            default=str,
        ),
        provider="anthropic",
        max_tokens=900,
        organization_id=org_id,
        brain_context=brain_context,
        request_id=get_current_request_id(),
        db=db,
    )
    provider = "anthropic"
    if claude_plan.startswith("Error:"):
        provider = "rule_based_fallback"
        top_items = limitations[:3]
        lines = [
            "Top Limits",
            *[f"- {x.name}: {x.evidence}" for x in top_items],
            "",
            "7-Day Plan",
            "- Backfill identity maps and weekly metrics for every active employee.",
            "- Re-run metrics + clone scoring daily and compare deltas.",
            "- Complete at least one OPEN role training plan per employee.",
            "",
            "30-Day Plan",
            "- Raise average clone score by >=15 points from baseline.",
            "- Reduce needs_support share below 30%.",
            "- Enforce approval SLA compliance and eliminate stale metrics.",
            "",
            "Guardrails",
            "- Keep all actions in suggest-only mode until metrics stabilize.",
            "- Require human approval for high-impact actions.",
            "",
            "Success Metrics",
            f"- Baseline average score: {avg_score:.2f}",
            f"- Current needs_support count: {needs_support}",
            f"- Current stale metrics count: {stale_metrics}",
        ]
        claude_plan = "\n".join(lines)

    next_actions = []
    if missing_identity > 0:
        next_actions.append(f"Map identities for {missing_identity} active employees.")
    if stale_metrics > 0:
        next_actions.append(f"Backfill weekly metrics for {stale_metrics} employees.")
    if pending_breaches > 0:
        next_actions.append(f"Clear {pending_breaches} approval SLA breaches.")
    if avg_score < 70:
        next_actions.append("Run weekly clone scoring + training-plan generation after each metrics refresh.")
    if not next_actions:
        next_actions.append("Maintain current cadence and optimize low-yield training tasks.")

    await record_action(
        db=db,
        event_type="clone_limitations_analyzed",
        actor_user_id=actor["id"],
        organization_id=org_id,
        entity_type="clone_control",
        entity_id=None,
        payload_json={
            "challenge": payload.challenge,
            "provider": provider,
            "limitation_count": len(limitations),
            "week_start_date": week_start.isoformat() if week_start else None,
        },
    )

    return CloneSelfDevelopRead(
        ok=True,
        mode="suggest_only",
        provider=provider,
        limitations=limitations,
        development_plan=claude_plan,
        next_actions=next_actions[:5],
        diagnostics=diagnostics,
    )


@router.post("/scenario/simulate", response_model=ScenarioSimulationRead)
async def scenario_simulate(
    payload: ScenarioSimulationRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> ScenarioSimulationRead:
    org_id = int(actor["org_id"])
    summary = await clone_brain.clone_org_summary(
        db,
        organization_id=org_id,
        week_start_date=None,
    )
    avg_score_raw = summary.get("avg_score", 0.0)
    avg_score = float(avg_score_raw) if isinstance(avg_score_raw, int | float) else 0.0
    dispatch = await clone_brain.build_dispatch_plan(
        db,
        organization_id=org_id,
        challenge=payload.challenge,
        week_start_date=None,
        top_n=payload.top_n,
    )
    baseline = max(5.0, min(95.0, 100.0 - avg_score))
    dispatch_avg = 0.0
    if dispatch:
        dispatch_avg = sum(float(item.get("overall_score", 0.0)) for item in dispatch) / len(dispatch)
    projected = max(1.0, baseline - ((dispatch_avg / 100.0) * payload.blockers_count * 2.5))
    drop_pct = round(((baseline - projected) / baseline) * 100.0, 2) if baseline > 0 else 0.0
    return ScenarioSimulationRead(
        challenge=payload.challenge,
        blockers_count=payload.blockers_count,
        baseline_risk_score=round(baseline, 2),
        projected_risk_score=round(projected, 2),
        projected_risk_drop_percent=drop_pct,
        recommended_dispatch=dispatch,  # type: ignore[arg-type]
    )
