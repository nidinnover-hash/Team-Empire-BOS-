from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.approval import Approval
from app.models.daily_run import DailyRun
from app.models.decision_trace import DecisionTrace
from app.models.event import Event
from app.models.finance import FinanceEntry
from app.schemas.intelligence import DecisionTraceCreate, ExecutiveDiffRead, ExecutiveSummaryRead
from app.services import finance as finance_service


def _bounded_score(score: float) -> float:
    return max(0.0, min(1.0, score))


def _risk_tier_from_confidence(confidence_score: float) -> str:
    if confidence_score >= 0.8:
        return "low"
    if confidence_score >= 0.55:
        return "medium"
    return "high"


async def create_decision_trace(db: AsyncSession, data: DecisionTraceCreate) -> DecisionTrace:
    trace = DecisionTrace(**data.model_dump())
    db.add(trace)
    await db.commit()
    await db.refresh(trace)
    return trace


async def list_decision_traces(
    db: AsyncSession,
    organization_id: int,
    limit: int = 20,
) -> list[DecisionTrace]:
    result = await db.execute(
        select(DecisionTrace)
        .where(DecisionTrace.organization_id == organization_id)
        .order_by(DecisionTrace.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def build_executive_summary(
    db: AsyncSession,
    organization_id: int,
    window_days: int = 7,
) -> ExecutiveSummaryRead:
    today = date.today()
    start_day = today - timedelta(days=max(window_days - 1, 0))
    start_dt = datetime.combine(start_day, time.min, tzinfo=timezone.utc)

    event_count_result = await db.execute(
        select(func.count(Event.id)).where(
            Event.organization_id == organization_id,
            Event.created_at >= start_dt,
        )
    )
    event_count = int(event_count_result.scalar() or 0)

    completed_run_result = await db.execute(
        select(func.count(DailyRun.id)).where(
            DailyRun.organization_id == organization_id,
            DailyRun.status == "completed",
            DailyRun.run_date >= start_day,
        )
    )
    completed_daily_runs = int(completed_run_result.scalar() or 0)

    pending_approvals_result = await db.execute(
        select(func.count(Approval.id)).where(
            Approval.organization_id == organization_id,
            Approval.status == "pending",
        )
    )
    pending_approvals = int(pending_approvals_result.scalar() or 0)

    finance_summary = await finance_service.get_summary(db, organization_id=organization_id)
    efficiency = await finance_service.get_expenditure_efficiency(
        db=db,
        organization_id=organization_id,
        window_days=window_days,
    )

    confidence = 0.2
    reasoning: list[str] = []
    if completed_daily_runs > 0:
        confidence += 0.25
        reasoning.append("Daily run execution exists in the selected window.")
    if event_count > 0:
        confidence += 0.2
        reasoning.append("Auditable operational events were recorded.")
    if (finance_summary.total_income + finance_summary.total_expense) > 0:
        confidence += 0.2
        reasoning.append("Finance data is present for this period.")
    if efficiency.efficiency_score >= 70:
        confidence += 0.15
        reasoning.append("Digital expenditure efficiency is in a healthy range.")
    else:
        reasoning.append("Digital expenditure efficiency is below the target range.")
    confidence = _bounded_score(confidence)
    risk_tier = _risk_tier_from_confidence(confidence)

    highlights = [
        f"{completed_daily_runs} completed daily runs in the last {window_days} days.",
        f"{event_count} auditable events captured.",
        f"Current balance: {finance_summary.balance:.2f}.",
    ]
    risks: list[str] = []
    if pending_approvals > 0:
        risks.append(f"{pending_approvals} approvals are still pending.")
    if efficiency.efficiency_score < 60:
        risks.append("Digital expenditure efficiency score is below target.")
    if not risks:
        risks.append("No immediate operational risk flags detected.")

    action_recommendations = [
        "Clear pending approvals queue to reduce decision latency.",
        "Keep daily run cadence consistent to improve execution predictability.",
        "Review low-ROI recurring digital expenses weekly.",
    ]

    summary_text = (
        "Execution cadence is stable."
        if completed_daily_runs >= max(1, window_days // 3)
        else "Execution cadence needs tighter daily-run consistency."
    )

    return ExecutiveSummaryRead(
        organization_id=organization_id,
        generated_at=datetime.now(timezone.utc),
        window_days=window_days,
        decision_summary=summary_text,
        confidence_score=confidence,
        risk_tier=risk_tier,
        reasoning=reasoning,
        kpis={
            "events_in_window": event_count,
            "completed_daily_runs": completed_daily_runs,
            "pending_approvals": pending_approvals,
            "finance_balance": round(finance_summary.balance, 2),
            "efficiency_score": efficiency.efficiency_score,
        },
        highlights=highlights,
        risks=risks,
        action_recommendations=action_recommendations,
    )


async def build_change_since_yesterday(db: AsyncSession, organization_id: int) -> ExecutiveDiffRead:
    today = date.today()
    yesterday = today - timedelta(days=1)

    today_start = datetime.combine(today, time.min, tzinfo=timezone.utc)
    tomorrow_start = datetime.combine(today + timedelta(days=1), time.min, tzinfo=timezone.utc)
    yesterday_start = datetime.combine(yesterday, time.min, tzinfo=timezone.utc)

    events_today_result = await db.execute(
        select(func.count(Event.id)).where(
            Event.organization_id == organization_id,
            Event.created_at >= today_start,
            Event.created_at < tomorrow_start,
        )
    )
    events_yesterday_result = await db.execute(
        select(func.count(Event.id)).where(
            Event.organization_id == organization_id,
            Event.created_at >= yesterday_start,
            Event.created_at < today_start,
        )
    )

    runs_today_result = await db.execute(
        select(func.count(DailyRun.id)).where(
            DailyRun.organization_id == organization_id,
            DailyRun.run_date == today,
            DailyRun.status == "completed",
        )
    )
    runs_yesterday_result = await db.execute(
        select(func.count(DailyRun.id)).where(
            DailyRun.organization_id == organization_id,
            DailyRun.run_date == yesterday,
            DailyRun.status == "completed",
        )
    )

    income_today_result = await db.execute(
        select(func.sum(FinanceEntry.amount)).where(
            FinanceEntry.organization_id == organization_id,
            FinanceEntry.entry_date == today,
            FinanceEntry.type == "income",
        )
    )
    income_yesterday_result = await db.execute(
        select(func.sum(FinanceEntry.amount)).where(
            FinanceEntry.organization_id == organization_id,
            FinanceEntry.entry_date == yesterday,
            FinanceEntry.type == "income",
        )
    )

    pending_approvals_result = await db.execute(
        select(func.count(Approval.id)).where(
            Approval.organization_id == organization_id,
            Approval.status == "pending",
        )
    )

    events_today = float(events_today_result.scalar() or 0)
    events_yesterday = float(events_yesterday_result.scalar() or 0)
    runs_today = float(runs_today_result.scalar() or 0)
    runs_yesterday = float(runs_yesterday_result.scalar() or 0)
    income_today = float(income_today_result.scalar() or 0)
    income_yesterday = float(income_yesterday_result.scalar() or 0)
    pending_approvals = float(pending_approvals_result.scalar() or 0)

    changes = [
        {
            "metric": "auditable_events",
            "yesterday": events_yesterday,
            "today": events_today,
            "delta": events_today - events_yesterday,
        },
        {
            "metric": "completed_daily_runs",
            "yesterday": runs_yesterday,
            "today": runs_today,
            "delta": runs_today - runs_yesterday,
        },
        {
            "metric": "income_logged",
            "yesterday": income_yesterday,
            "today": income_today,
            "delta": income_today - income_yesterday,
        },
    ]

    narrative = (
        "Operational activity increased versus yesterday."
        if (events_today + runs_today) >= (events_yesterday + runs_yesterday)
        else "Operational activity decreased versus yesterday."
    )

    event_delta = events_today - events_yesterday
    run_delta = runs_today - runs_yesterday
    income_delta = income_today - income_yesterday

    confidence = 0.35
    reasoning: list[str] = []
    if (events_today + events_yesterday) > 0:
        confidence += 0.2
        reasoning.append("Event stream data exists for both days.")
    if (runs_today + runs_yesterday) > 0:
        confidence += 0.2
        reasoning.append("Daily run history exists for comparison.")
    if (income_today + income_yesterday) > 0:
        confidence += 0.15
        reasoning.append("Income data exists for day-over-day analysis.")
    if pending_approvals <= 3:
        confidence += 0.1
        reasoning.append("Pending approvals are within manageable range.")
    else:
        reasoning.append("Pending approvals are elevated and may block execution.")
    confidence = _bounded_score(confidence)
    risk_tier = _risk_tier_from_confidence(confidence)

    what_changed = (
        f"Events: {int(events_yesterday)} -> {int(events_today)}, "
        f"daily runs: {int(runs_yesterday)} -> {int(runs_today)}, "
        f"income logged: {income_yesterday:.2f} -> {income_today:.2f}."
    )
    risk_increased = (
        "Yes. Execution signals dropped or approval pressure is high."
        if (event_delta < 0 or run_delta < 0 or pending_approvals > 3)
        else "No material risk increase detected."
    )
    opportunity_increased = (
        "Yes. More activity and/or revenue signal improved versus yesterday."
        if (event_delta > 0 or run_delta > 0 or income_delta > 0)
        else "No clear opportunity increase signal."
    )
    urgent_decision = (
        f"Resolve pending approvals queue ({int(pending_approvals)} pending) first."
        if pending_approvals > 0
        else "No urgent approval bottleneck; prioritize top revenue-linked execution tasks."
    )

    return ExecutiveDiffRead(
        organization_id=organization_id,
        date_today=today,
        date_yesterday=yesterday,
        changes=changes,
        what_changed_since_yesterday=what_changed,
        risk_increased=risk_increased,
        opportunity_increased=opportunity_increased,
        urgent_decision=urgent_decision,
        confidence_score=confidence,
        risk_tier=risk_tier,
        reasoning=reasoning,
        narrative=narrative,
    )
