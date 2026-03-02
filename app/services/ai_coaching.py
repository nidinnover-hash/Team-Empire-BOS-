"""AI-driven coaching and recommendation engine.

Uses call_ai() to generate coaching reports from performance data.
All recommendations create CoachingReport records with status=pending,
requiring CEO/ADMIN approval before acting on them.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.coaching_report import CoachingReport
from app.services import performance as perf_service

logger = logging.getLogger(__name__)


async def _call_ai_safe(system_prompt: str, user_message: str) -> str:
    """Call AI with graceful fallback if no provider is configured."""
    try:
        from app.services.ai_router import call_ai
        return await call_ai(
            system_prompt=system_prompt,
            user_message=user_message,
            provider="openai",
            max_tokens=1500,
        )
    except Exception as exc:
        logger.warning("AI coaching call failed: %s", exc, exc_info=True)
        return json.dumps({
            "recommendations": [
                {"area": "General", "suggestion": "Review employee work patterns and adjust workload distribution.", "priority": "medium"},
            ],
            "summary": "AI analysis unavailable. Manual review recommended.",
            "_fallback": True,
            "_error": str(exc),
        })


async def generate_employee_coaching(
    db: AsyncSession,
    employee_id: int,
    org_id: int,
) -> dict[str, Any] | None:
    perf = await perf_service.get_employee_performance(db, employee_id, org_id, days=30)
    if perf is None:
        return None

    system_prompt = (
        "You are an AI performance coach for a business operating system. "
        "Analyze the employee's performance data and provide actionable coaching recommendations. "
        "Return JSON with keys: recommendations (list of {area, suggestion, priority}), summary (string)."
    )
    user_message = (
        f"Employee: {perf.employee_name}\n"
        f"Average hours/day: {perf.avg_hours}\n"
        f"Focus ratio: {perf.avg_focus_ratio}\n"
        f"Tasks/day: {perf.avg_tasks_per_day}\n"
        f"Composite score: {perf.composite_score}\n"
        f"Days tracked: {perf.days_tracked}\n"
        f"Total meetings minutes: {perf.total_meetings_minutes}\n"
        "Provide 3-5 specific coaching recommendations."
    )

    ai_response = await _call_ai_safe(system_prompt, user_message)

    try:
        parsed = json.loads(ai_response)
    except (json.JSONDecodeError, TypeError):
        parsed = {"recommendations": [], "summary": ai_response}

    report = CoachingReport(
        organization_id=org_id,
        employee_id=employee_id,
        report_type="employee",
        title=f"AI Coaching: {perf.employee_name}",
        summary=parsed.get("summary", ""),
        recommendations_json=parsed,
        status="pending",
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)

    return {
        "report_id": report.id,
        "employee_id": employee_id,
        "employee_name": perf.employee_name,
        "composite_score": perf.composite_score,
        "recommendations": parsed.get("recommendations", []),
        "summary": parsed.get("summary", ""),
        "status": "pending",
    }


async def generate_department_recommendations(
    db: AsyncSession,
    department_id: int,
    org_id: int,
) -> dict[str, Any] | None:
    dept_perf = await perf_service.get_department_performance(db, department_id, org_id, days=30)
    if dept_perf is None:
        return None

    system_prompt = (
        "You are an AI business strategist. Analyze department performance data "
        "and provide improvement recommendations. "
        "Return JSON with keys: recommendations (list of {area, suggestion, priority}), summary (string)."
    )
    top_info = ", ".join(
        f"{tp.employee_name}(score={tp.composite_score})" for tp in dept_perf.top_performers[:3]
    )
    user_message = (
        f"Department: {dept_perf.department_name}\n"
        f"Employee count: {dept_perf.employee_count}\n"
        f"Average hours: {dept_perf.avg_hours}\n"
        f"Focus ratio: {dept_perf.avg_focus_ratio}\n"
        f"Tasks/day: {dept_perf.avg_tasks_per_day}\n"
        f"Top performers: {top_info or 'none'}\n"
        "Provide 3-5 department-level recommendations."
    )

    ai_response = await _call_ai_safe(system_prompt, user_message)

    try:
        parsed = json.loads(ai_response)
    except (json.JSONDecodeError, TypeError):
        parsed = {"recommendations": [], "summary": ai_response}

    report = CoachingReport(
        organization_id=org_id,
        department_id=department_id,
        report_type="department",
        title=f"AI Recommendations: {dept_perf.department_name}",
        summary=parsed.get("summary", ""),
        recommendations_json=parsed,
        status="pending",
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)

    return {
        "report_id": report.id,
        "department_id": department_id,
        "department_name": dept_perf.department_name,
        "recommendations": parsed.get("recommendations", []),
        "summary": parsed.get("summary", ""),
        "status": "pending",
    }


async def generate_org_improvement_plan(
    db: AsyncSession,
    org_id: int,
) -> dict[str, Any]:
    org_perf = await perf_service.get_org_performance(db, org_id, days=30)

    system_prompt = (
        "You are a CEO-level AI strategist. Analyze organization-wide performance data "
        "and provide a strategic improvement plan. "
        "Return JSON with keys: recommendations (list of {area, suggestion, priority}), summary (string)."
    )
    dept_info = "; ".join(
        f"{d.department_name}: {d.employee_count} employees, score avg focus={d.avg_focus_ratio}"
        for d in org_perf.departments[:5]
    )
    user_message = (
        f"Organization: {org_perf.total_employees} employees, {org_perf.total_departments} departments\n"
        f"Average hours: {org_perf.avg_hours}\n"
        f"Focus ratio: {org_perf.avg_focus_ratio}\n"
        f"Tasks/day: {org_perf.avg_tasks_per_day}\n"
        f"Departments: {dept_info or 'none'}\n"
        "Provide 3-5 strategic recommendations for the CEO."
    )

    ai_response = await _call_ai_safe(system_prompt, user_message)

    try:
        parsed = json.loads(ai_response)
    except (json.JSONDecodeError, TypeError):
        parsed = {"recommendations": [], "summary": ai_response}

    report = CoachingReport(
        organization_id=org_id,
        report_type="org",
        title="AI Org Improvement Plan",
        summary=parsed.get("summary", ""),
        recommendations_json=parsed,
        status="pending",
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)

    return {
        "report_id": report.id,
        "recommendations": parsed.get("recommendations", []),
        "summary": parsed.get("summary", ""),
        "status": "pending",
    }
