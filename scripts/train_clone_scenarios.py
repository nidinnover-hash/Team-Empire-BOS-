"""
Run "recording/coaching" and clone training flows for multiple situations.

Usage:
  .venv\\Scripts\\python.exe scripts\\train_clone_scenarios.py
  .venv\\Scripts\\python.exe scripts\\train_clone_scenarios.py --org-id 1 --week-start 2026-02-23
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import date, timedelta
from pathlib import Path
import sys

from sqlalchemy.exc import OperationalError

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import AsyncSessionLocal
from app.schemas.data_collection import CloneProTrainingRequest, MeetingCoachingRequest
from app.services import clone_brain, clone_control, data_collection, organization as organization_service


def _default_week_start() -> date:
    today = date.today()
    return today - timedelta(days=today.weekday())


def _build_scenarios() -> list[dict[str, object]]:
    return [
        {
            "name": "client_escalation",
            "training": CloneProTrainingRequest(
                source="situation_client_escalation",
                preferred_name="Nidin",
                communication_style="Calm, direct, and accountable under pressure.",
                top_priorities=[
                    "Resolve critical client blockers within same business day",
                    "Protect trust with transparent updates and clear ownership",
                    "Convert escalations into process improvements",
                ],
                operating_rules=[
                    "Acknowledge issue in the first response",
                    "Commit a concrete next update time",
                    "Escalate early when timeline risk is identified",
                ],
                daily_focus=[
                    "Review open escalations and owners by 10 AM",
                    "Close at least one recurring root cause this week",
                ],
                domain_notes=[
                    "Clients value speed + clarity over perfection during incidents.",
                ],
            ),
            "coaching": MeetingCoachingRequest(
                source="recording_client_escalation",
                objective="support",
                speaker_name="Account Lead",
                consent_confirmed=True,
                transcript=(
                    "Thanks for raising this quickly. I understand the delay affected your launch. "
                    "Can we align on the top two blockers first? "
                    "We can ship a temporary fix by 4 PM and the full correction tomorrow morning. "
                    "Would that timeline work for your team? "
                    "If anything changes, I will update you before 3 PM with the latest status."
                ),
            ),
        },
        {
            "name": "sales_negotiation",
            "training": CloneProTrainingRequest(
                source="situation_sales_negotiation",
                preferred_name="Nidin",
                communication_style="Consultative and ROI-focused with concise commercial framing.",
                top_priorities=[
                    "Qualify budget and decision timeline early",
                    "Anchor discussion on measurable business outcomes",
                    "Drive every call to a defined next step",
                ],
                operating_rules=[
                    "Ask at least three discovery questions before proposing",
                    "Confirm objection type before countering",
                    "Summarize agreement and next action at call end",
                ],
                daily_focus=[
                    "Run focused pipeline reviews with close-date risk flags",
                    "Prioritize high-fit accounts with executive urgency",
                ],
                domain_notes=[
                    "Discount only against commitment scope, not against uncertainty.",
                ],
            ),
            "coaching": MeetingCoachingRequest(
                source="recording_sales_negotiation",
                objective="sales",
                speaker_name="Sales Manager",
                consent_confirmed=True,
                transcript=(
                    "I appreciate the budget concern. What outcome matters most this quarter? "
                    "If we reduce manual review by 30%, would that justify the investment? "
                    "We can start with a pilot and confirm ROI in two weeks. "
                    "What would prevent you from approving this today? "
                    "If we align on terms now, can we begin implementation Monday?"
                ),
            ),
        },
        {
            "name": "team_execution_crunch",
            "training": CloneProTrainingRequest(
                source="situation_team_execution_crunch",
                preferred_name="Nidin",
                communication_style="High-clarity prioritization with fast feedback loops.",
                top_priorities=[
                    "Sequence work by business impact and dependency order",
                    "Prevent hidden blockers with daily check-ins",
                    "Protect focus time for deep execution",
                ],
                operating_rules=[
                    "One owner per deliverable",
                    "Escalate blockers within two hours",
                    "Track completion against weekly score targets",
                ],
                daily_focus=[
                    "Finalize top 3 execution goals before noon",
                    "Review end-of-day progress and unblock tomorrow's work",
                ],
                domain_notes=[
                    "Clarity of ownership is the fastest lever for throughput gains.",
                ],
            ),
            "coaching": MeetingCoachingRequest(
                source="recording_team_execution_crunch",
                objective="general",
                speaker_name="Ops Manager",
                consent_confirmed=True,
                transcript=(
                    "Let's focus on what can ship this week. "
                    "Which dependency is currently the biggest blocker? "
                    "I can support that handoff if we commit the owner now. "
                    "Please confirm timeline by 5 PM and post the status update in the team channel. "
                    "If risk grows, escalate before tomorrow's standup."
                ),
            ),
        },
    ]


async def _run(org_id: int | None, week_start: date) -> None:
    scenarios = _build_scenarios()
    async with AsyncSessionLocal() as db:
        if org_id is None:
            org = await organization_service.ensure_default_organization(db)
            org_id = int(org.id)

        print(f"Training org_id={org_id} week_start={week_start.isoformat()}")
        print(f"Situations: {len(scenarios)}")

        for scenario in scenarios:
            name = str(scenario["name"])
            training = scenario["training"]
            coaching = scenario["coaching"]

            train_result = await data_collection.train_clone_pro(
                db=db,
                org_id=org_id,
                data=training,
            )
            coach_result = await data_collection.analyze_meeting_transcript(
                db=db,
                org_id=org_id,
                data=coaching,
            )
            print(
                f"- {name}: profile={train_result.profile_memory_written}, "
                f"context={train_result.daily_context_written}, notes={train_result.notes_written}, "
                f"tone={coach_result.tone_profile}, note_id={coach_result.note_id}"
            )

        score_result = await clone_brain.train_weekly_clone_scores(
            db=db,
            organization_id=org_id,
            week_start_date=week_start,
        )
        plan_result = await clone_control.generate_role_training_plans(
            db=db,
            organization_id=org_id,
            week_start_date=week_start,
        )
        summary = await clone_brain.clone_org_summary(
            db=db,
            organization_id=org_id,
            week_start_date=week_start,
        )
        print(
            "Clone scoring:",
            f"employees_scored={score_result.get('employees_scored', 0)}",
            f"plans_generated={plan_result.get('plans_generated', 0)}",
            f"avg_score={summary.get('avg_score', 0.0)}",
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run recording/coaching + clone training across predefined situations.",
    )
    parser.add_argument("--org-id", type=int, default=None, help="Organization ID. Default: ensure default org.")
    parser.add_argument(
        "--week-start",
        type=str,
        default=_default_week_start().isoformat(),
        help="Week start date in YYYY-MM-DD format.",
    )
    args = parser.parse_args()

    try:
        week_start = date.fromisoformat(args.week_start)
    except ValueError as exc:
        raise SystemExit(f"Invalid --week-start value: {args.week_start}") from exc

    try:
        asyncio.run(_run(org_id=args.org_id, week_start=week_start))
    except OperationalError as exc:
        raise SystemExit(
            "Database schema is behind current models. "
            "Run migrations first: alembic upgrade head\n"
            f"Original error: {exc.__class__.__name__}: {exc}"
        ) from exc


if __name__ == "__main__":
    main()
