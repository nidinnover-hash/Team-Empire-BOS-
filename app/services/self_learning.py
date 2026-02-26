from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.approval import Approval
from app.models.clone_control import CloneLearningFeedback
from app.models.decision_log import DecisionLog
from app.models.policy_rule import PolicyRule
from app.models.self_learning_run import SelfLearningRun
from app.services import clone_brain, clone_control, policy_service


async def learning_signals(
    db: AsyncSession,
    *,
    organization_id: int,
    lookback_days: int = 30,
) -> dict[str, Any]:
    cutoff = datetime.now(UTC) - timedelta(days=max(1, lookback_days))

    approval_rows = (
        await db.execute(
            select(Approval.status, func.count(Approval.id))
            .where(
                Approval.organization_id == organization_id,
                Approval.created_at >= cutoff,
            )
            .group_by(Approval.status)
        )
    ).all()
    approval_counts = {str(status): int(count) for status, count in approval_rows}
    approved = approval_counts.get("approved", 0)
    rejected = approval_counts.get("rejected", 0)
    approval_total = approved + rejected
    approval_accept_rate = round((approved / approval_total), 4) if approval_total else 0.0

    feedback_avg = (
        await db.execute(
            select(func.avg(CloneLearningFeedback.outcome_score)).where(
                CloneLearningFeedback.organization_id == organization_id,
                CloneLearningFeedback.created_at >= cutoff,
            )
        )
    ).scalar_one_or_none()
    feedback_count = (
        await db.execute(
            select(func.count(CloneLearningFeedback.id)).where(
                CloneLearningFeedback.organization_id == organization_id,
                CloneLearningFeedback.created_at >= cutoff,
            )
        )
    ).scalar_one()

    decision_rows = (
        await db.execute(
            select(DecisionLog.decision_type, func.count(DecisionLog.id))
            .where(
                DecisionLog.organization_id == organization_id,
                DecisionLog.created_at >= cutoff,
            )
            .group_by(DecisionLog.decision_type)
        )
    ).all()
    decision_counts = {str(kind): int(count) for kind, count in decision_rows}

    active_policy_count = (
        await db.execute(
            select(func.count(PolicyRule.id)).where(
                PolicyRule.organization_id == organization_id,
                PolicyRule.is_active.is_(True),
            )
        )
    ).scalar_one()

    avg_feedback = float(feedback_avg) if feedback_avg is not None else 0.5
    learning_intelligence_score = int(
        max(
            0,
            min(
                100,
                round(
                    (approval_accept_rate * 40.0)
                    + (avg_feedback * 40.0)
                    + min(20.0, float(active_policy_count or 0) * 2.0)
                ),
                0,
            ),
        )
    )

    return {
        "window_days": int(lookback_days),
        "approval_counts": approval_counts,
        "approval_accept_rate": approval_accept_rate,
        "feedback_count": int(feedback_count or 0),
        "feedback_avg_outcome": round(avg_feedback, 4),
        "decision_counts": decision_counts,
        "active_policy_count": int(active_policy_count or 0),
        "learning_intelligence_score": learning_intelligence_score,
    }


async def train_weekly_intelligence(
    db: AsyncSession,
    *,
    organization_id: int,
) -> dict[str, Any]:
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    clone_scores = await clone_brain.train_weekly_clone_scores(
        db,
        organization_id=organization_id,
        week_start_date=week_start,
    )
    training_plans = await clone_control.generate_role_training_plans(
        db,
        organization_id=organization_id,
        week_start_date=week_start,
    )
    policy_drafts = await policy_service.generate_policy_drafts(db, organization_id)
    signals = await learning_signals(db, organization_id=organization_id, lookback_days=30)
    return {
        "week_start_date": week_start.isoformat(),
        "clone_scores": clone_scores,
        "training_plans": training_plans,
        "policy_drafts_created": len(policy_drafts),
        "learning_signals_30d": signals,
    }


async def claim_weekly_run(
    db: AsyncSession,
    *,
    organization_id: int,
    week_start_date: date,
    requested_by: int | None,
) -> tuple[bool, SelfLearningRun]:
    row = SelfLearningRun(
        organization_id=organization_id,
        week_start_date=week_start_date,
        requested_by=requested_by,
        status="running",
        details_json={},
    )
    db.add(row)
    try:
        await db.commit()
        await db.refresh(row)
        return True, row
    except IntegrityError:
        await db.rollback()
        existing = (
            await db.execute(
                select(SelfLearningRun).where(
                    SelfLearningRun.organization_id == organization_id,
                    SelfLearningRun.week_start_date == week_start_date,
                )
            )
        ).scalar_one()
        return False, existing


async def complete_weekly_run(
    db: AsyncSession,
    *,
    run_id: int,
    status: str,
    details: dict[str, Any],
) -> None:
    row = (
        await db.execute(
            select(SelfLearningRun).where(SelfLearningRun.id == run_id)
        )
    ).scalar_one_or_none()
    if row is None:
        return
    row.status = status
    row.details_json = details
    row.updated_at = datetime.now(UTC)
    db.add(row)
    await db.commit()
