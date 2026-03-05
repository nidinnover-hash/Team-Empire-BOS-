"""
Tests for app/services/report_service.py

Covers:
  - generate_weekly_report for each report_type (team_health, project_risk, founder_review)
  - get_report (exists / not exists)
  - Upsert (overwrite) behaviour
  - Report content format (markdown sections/headers)
  - No-employees case
  - Metric data flows through to rendered markdown
  - Org isolation
"""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee
from app.models.ops_metrics import CodeMetricWeekly, CommsMetricWeekly, TaskMetricWeekly
from app.models.weekly_report import WeeklyReport
from app.services.report_service import generate_weekly_report, get_report

WEEK = date(2026, 2, 23)  # Monday


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

async def _add_employee(db: AsyncSession, org_id: int, name: str, job_title: str = "Engineer") -> Employee:
    emp = Employee(
        organization_id=org_id,
        name=name,
        job_title=job_title,
        email=f"{name.lower().replace(' ', '.')}@test.com",
        is_active=True,
    )
    db.add(emp)
    await db.flush()
    return emp


async def _add_task_metric(
    db: AsyncSession, org_id: int, emp_id: int, week: date, *,
    assigned: int = 10, completed: int = 8, on_time: float = 0.9, reopens: int = 0,
) -> TaskMetricWeekly:
    m = TaskMetricWeekly(
        organization_id=org_id,
        employee_id=emp_id,
        week_start_date=week,
        tasks_assigned=assigned,
        tasks_completed=completed,
        on_time_rate=on_time,
        avg_cycle_time_hours=4.0,
        reopen_count=reopens,
    )
    db.add(m)
    await db.flush()
    return m


async def _add_code_metric(
    db: AsyncSession, org_id: int, emp_id: int, week: date, *,
    prs_opened: int = 3, prs_merged: int = 2, reviews: int = 5, issues: int = 2, files: int = 15,
) -> CodeMetricWeekly:
    m = CodeMetricWeekly(
        organization_id=org_id,
        employee_id=emp_id,
        week_start_date=week,
        commits=12,
        prs_opened=prs_opened,
        prs_merged=prs_merged,
        reviews_done=reviews,
        issue_links=issues,
        files_touched_count=files,
    )
    db.add(m)
    await db.flush()
    return m


async def _add_comms_metric(
    db: AsyncSession, org_id: int, emp_id: int, week: date, *,
    sent: int = 20, replied: int = 15, escalations: int = 1,
) -> CommsMetricWeekly:
    m = CommsMetricWeekly(
        organization_id=org_id,
        employee_id=emp_id,
        week_start_date=week,
        emails_sent=sent,
        emails_replied=replied,
        median_reply_time_minutes=45.0,
        escalation_count=escalations,
    )
    db.add(m)
    await db.flush()
    return m


# ---------------------------------------------------------------------------
# 1. generate_weekly_report — team_health
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_team_health(db: AsyncSession):
    report = await generate_weekly_report(db, org_id=1, week_start=WEEK, report_type="team_health")

    assert report.id is not None
    assert report.organization_id == 1
    assert report.week_start_date == WEEK
    assert report.report_type == "team_health"
    assert report.content_markdown.startswith("# Team Health Report")


# ---------------------------------------------------------------------------
# 2. generate_weekly_report — project_risk
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_project_risk(db: AsyncSession):
    report = await generate_weekly_report(db, org_id=1, week_start=WEEK, report_type="project_risk")

    assert report.id is not None
    assert report.organization_id == 1
    assert report.week_start_date == WEEK
    assert report.report_type == "project_risk"
    assert report.content_markdown.startswith("# Project Risk Report")


# ---------------------------------------------------------------------------
# 3. generate_weekly_report — founder_review
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_founder_review(db: AsyncSession):
    report = await generate_weekly_report(db, org_id=1, week_start=WEEK, report_type="founder_review")

    assert report.id is not None
    assert report.organization_id == 1
    assert report.week_start_date == WEEK
    assert report.report_type == "founder_review"
    assert report.content_markdown.startswith("# Founder Decision Review")


# ---------------------------------------------------------------------------
# 4. get_report — exists
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_report_exists(db: AsyncSession):
    created = await generate_weekly_report(db, org_id=1, week_start=WEEK, report_type="team_health")
    fetched = await get_report(db, org_id=1, week_start=WEEK, report_type="team_health")

    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.content_markdown == created.content_markdown


# ---------------------------------------------------------------------------
# 5. get_report — not exists
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_report_not_exists(db: AsyncSession):
    result = await get_report(db, org_id=1, week_start=WEEK, report_type="team_health")
    assert result is None


# ---------------------------------------------------------------------------
# 6. Upsert / overwrite behaviour
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_overwrites_existing(db: AsyncSession):
    """Generating twice for the same week+type should update the existing row, not create a second."""
    r1 = await generate_weekly_report(db, org_id=1, week_start=WEEK, report_type="team_health")
    first_id = r1.id

    # Add an employee so the second generation produces different content
    await _add_employee(db, org_id=1, name="Alice Overwrite")
    await db.flush()

    r2 = await generate_weekly_report(db, org_id=1, week_start=WEEK, report_type="team_health")

    # Same row was updated (same id)
    assert r2.id == first_id
    # Content now contains the new employee
    assert "Alice Overwrite" in r2.content_markdown

    # Verify only one row in the table for this week+type
    count_result = await db.execute(
        select(WeeklyReport).where(
            WeeklyReport.organization_id == 1,
            WeeklyReport.week_start_date == WEEK,
            WeeklyReport.report_type == "team_health",
        )
    )
    rows = list(count_result.scalars().all())
    assert len(rows) == 1


# ---------------------------------------------------------------------------
# 7. Report content format — verify markdown headers/sections
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_report_content_format(db: AsyncSession):
    await _add_employee(db, org_id=1, name="Bob Format", job_title="Senior Dev")
    await db.flush()

    report = await generate_weekly_report(db, org_id=1, week_start=WEEK, report_type="team_health")
    md = report.content_markdown

    # Top-level heading
    assert "# Team Health Report" in md
    # Week reference
    assert WEEK.isoformat() in md
    # Summary table header
    assert "## Summary Scores" in md
    assert "| Employee | Delivery | Quality Proxy | Comms Proxy | Initiative |" in md
    # Metric definitions section
    assert "## Metric Definitions" in md
    # Detailed breakdown section with employee name and role
    assert "## Detailed Breakdown" in md
    assert "### Bob Format (Senior Dev)" in md


# ---------------------------------------------------------------------------
# 8. generate_weekly_report with no employees
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_with_no_employees(db: AsyncSession):
    """Even with zero employees, a valid markdown report should be produced."""
    report = await generate_weekly_report(db, org_id=1, week_start=WEEK, report_type="team_health")

    assert report.content_markdown.startswith("# Team Health Report")
    assert "## Summary Scores" in report.content_markdown
    assert "## Metric Definitions" in report.content_markdown

    # project_risk with no employees should show "No at-risk signals"
    risk_report = await generate_weekly_report(db, org_id=1, week_start=WEEK, report_type="project_risk")
    assert "No at-risk signals detected this week." in risk_report.content_markdown

    # founder_review with no employees should show team size 0
    founder_report = await generate_weekly_report(db, org_id=1, week_start=WEEK, report_type="founder_review")
    assert "Team size: 0 active employees" in founder_report.content_markdown
    assert "Tasks: 0/0 completed across team" in founder_report.content_markdown


# ---------------------------------------------------------------------------
# 9. generate_weekly_report with metric data
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_with_metric_data(db: AsyncSession):
    """Add Employee + metric rows and verify the report references them."""
    emp = await _add_employee(db, org_id=1, name="Charlie Metrics", job_title="Backend Dev")

    await _add_task_metric(db, 1, emp.id, WEEK, assigned=10, completed=8, on_time=0.9, reopens=1)
    await _add_code_metric(db, 1, emp.id, WEEK, prs_opened=5, prs_merged=4, reviews=7, issues=3, files=20)
    await _add_comms_metric(db, 1, emp.id, WEEK, sent=30, replied=25, escalations=2)
    await db.flush()

    # --- team_health ---
    th = await generate_weekly_report(db, org_id=1, week_start=WEEK, report_type="team_health")
    md = th.content_markdown

    # Employee name in the summary table row
    assert "Charlie Metrics" in md
    # Delivery = 8/10 = 80%
    assert "80%" in md
    # Detailed breakdown should contain raw numbers
    assert "8/10 completed" in md
    assert "5 PRs opened" in md
    assert "30 sent" in md
    assert "25 replies" in md
    assert "2 escalations" in md

    # --- project_risk ---
    pr = await generate_weekly_report(db, org_id=1, week_start=WEEK, report_type="project_risk")
    # 8/10 = 0.8 >= 0.5 so completion is fine; on_time 0.9 >= 0.6; reopens 1 <= 2
    # No risk should be flagged
    assert "No at-risk signals detected this week." in pr.content_markdown

    # --- founder_review ---
    fr = await generate_weekly_report(db, org_id=1, week_start=WEEK, report_type="founder_review")
    assert "1 active employees" in fr.content_markdown
    assert "8/10 completed across team" in fr.content_markdown


# ---------------------------------------------------------------------------
# 10. Org isolation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_org_isolation(db: AsyncSession):
    """A report generated for org 1 must not be retrievable via org 2."""
    await generate_weekly_report(db, org_id=1, week_start=WEEK, report_type="team_health")

    # Same week+type but different org — should be None
    result = await get_report(db, org_id=2, week_start=WEEK, report_type="team_health")
    assert result is None

    # Generate for org 2 separately and verify independence
    r2 = await generate_weekly_report(db, org_id=2, week_start=WEEK, report_type="team_health")
    assert r2.organization_id == 2

    r1 = await get_report(db, org_id=1, week_start=WEEK, report_type="team_health")
    assert r1 is not None
    assert r1.organization_id == 1
    assert r1.id != r2.id
