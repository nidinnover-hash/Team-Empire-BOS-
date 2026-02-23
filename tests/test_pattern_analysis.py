"""Tests for pattern analysis service — feedback loop from ops intelligence to AI context."""
import hashlib
import json
from datetime import date, datetime, timedelta, timezone

from app.core.deps import get_db
from app.core.security import create_access_token
from app.main import app as fastapi_app
from app.models.decision_log import DecisionLog
from app.models.employee import Employee
from app.models.event import Event
from app.models.ops_metrics import CodeMetricWeekly, TaskMetricWeekly
from app.models.organization import Organization
from app.models.policy_rule import PolicyRule
from app.models.user import User
from app.services.pattern_analysis import build_work_patterns_context


def _monday_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


async def _get_db_session():
    override = fastapi_app.dependency_overrides[get_db]
    agen = override()
    return await agen.__anext__(), agen


async def _seed(org_id: int = 1) -> None:
    session, agen = await _get_db_session()
    try:
        session.add(Organization(id=org_id, name=f"Org {org_id}", slug=f"org-{org_id}"))
        session.add(User(id=1, email="ceo@org.com", name="CEO", role="CEO", organization_id=org_id, password_hash="x"))
        await session.commit()
    except Exception:
        await session.rollback()
    finally:
        await agen.aclose()


async def test_empty_patterns_returns_empty(client):
    """No data = no patterns block."""
    await _seed()
    session, agen = await _get_db_session()
    try:
        result = await build_work_patterns_context(session, org_id=1, weeks=2)
        assert result == ""
    finally:
        await agen.aclose()


async def test_task_metrics_appear_in_patterns(client):
    """Task metrics should be surfaced in the work patterns context."""
    await _seed()
    session, agen = await _get_db_session()
    try:
        emp = Employee(organization_id=1, name="Alice", email="alice@test.com", is_active=True)
        session.add(emp)
        await session.flush()

        monday = _monday_of(date.today())
        session.add(TaskMetricWeekly(
            organization_id=1, employee_id=emp.id, week_start_date=monday,
            tasks_assigned=10, tasks_completed=8, on_time_rate=0.75, reopen_count=1,
        ))
        await session.commit()

        result = await build_work_patterns_context(session, org_id=1, weeks=2)
        assert "Alice" in result
        assert "8/10 completed" in result
        assert "75% on-time" in result
    finally:
        await agen.aclose()


async def test_low_on_time_flagged(client):
    """Low on-time rate should trigger a flag in patterns."""
    await _seed()
    session, agen = await _get_db_session()
    try:
        emp = Employee(organization_id=1, name="Bob", email="bob@test.com", is_active=True)
        session.add(emp)
        await session.flush()

        monday = _monday_of(date.today())
        session.add(TaskMetricWeekly(
            organization_id=1, employee_id=emp.id, week_start_date=monday,
            tasks_assigned=10, tasks_completed=4, on_time_rate=0.3, reopen_count=5,
        ))
        await session.commit()

        result = await build_work_patterns_context(session, org_id=1, weeks=2)
        assert "LOW on-time rate" in result
        assert "5 reopens" in result
    finally:
        await agen.aclose()


async def test_code_metrics_in_patterns(client):
    """Code metrics should appear in the work patterns context."""
    await _seed()
    session, agen = await _get_db_session()
    try:
        emp = Employee(organization_id=1, name="Charlie", email="c@test.com", is_active=True)
        session.add(emp)
        await session.flush()

        monday = _monday_of(date.today())
        session.add(CodeMetricWeekly(
            organization_id=1, employee_id=emp.id, week_start_date=monday,
            prs_opened=5, prs_merged=3, reviews_done=7, files_touched_count=20,
        ))
        await session.commit()

        result = await build_work_patterns_context(session, org_id=1, weeks=2)
        assert "Charlie" in result
        assert "5 PRs opened" in result
        assert "3 merged" in result
    finally:
        await agen.aclose()


async def test_decision_patterns_in_context(client):
    """Decision log patterns should be summarized."""
    await _seed()
    session, agen = await _get_db_session()
    try:
        for i in range(5):
            session.add(DecisionLog(
                organization_id=1, created_by=1,
                decision_type="approve" if i < 4 else "reject",
                context=f"Budget request #{i}", objective="Improve team",
                reason="Data-backed",
            ))
        await session.commit()

        result = await build_work_patterns_context(session, org_id=1, weeks=2)
        assert "approve: 4 (80%)" in result
        assert "reject: 1 (20%)" in result
    finally:
        await agen.aclose()


async def test_approval_behavior_in_context(client):
    """Approval/rejection events should be summarized."""
    await _seed()
    session, agen = await _get_db_session()
    try:
        for _ in range(3):
            session.add(Event(
                organization_id=1, event_type="approval_approved",
                actor_user_id=1,
            ))
        session.add(Event(
            organization_id=1, event_type="approval_rejected",
            actor_user_id=1,
        ))
        for _ in range(5):
            session.add(Event(
                organization_id=1, event_type="agent_chat",
                actor_user_id=1,
            ))
        await session.commit()

        result = await build_work_patterns_context(session, org_id=1, weeks=2)
        assert "3/4" in result  # 3 approvals out of 4
        assert "75% approval rate" in result
        assert "5 conversations" in result
    finally:
        await agen.aclose()


async def test_active_policies_in_context(client):
    """Active policies should be listed in the context."""
    await _seed()
    session, agen = await _get_db_session()
    try:
        session.add(PolicyRule(
            organization_id=1, title="Auto-approve small budgets",
            rule_text="Budgets under $500 may be auto-approved", is_active=True,
        ))
        session.add(PolicyRule(
            organization_id=1, title="Draft policy",
            rule_text="Some draft rule", is_active=False,
        ))
        await session.commit()

        result = await build_work_patterns_context(session, org_id=1, weeks=2)
        assert "Auto-approve small budgets" in result
        assert "Draft policy" not in result  # inactive policies excluded
    finally:
        await agen.aclose()


async def test_patterns_injected_into_memory_context(client):
    """build_memory_context() should include work patterns when data exists."""
    await _seed()
    session, agen = await _get_db_session()
    try:
        emp = Employee(organization_id=1, name="Dave", email="d@test.com", is_active=True)
        session.add(emp)
        await session.flush()

        monday = _monday_of(date.today())
        session.add(TaskMetricWeekly(
            organization_id=1, employee_id=emp.id, week_start_date=monday,
            tasks_assigned=6, tasks_completed=5, on_time_rate=0.9, reopen_count=0,
        ))
        await session.commit()

        from app.services.memory import build_memory_context
        ctx = await build_memory_context(session, organization_id=1)
        assert "[WORK PATTERNS" in ctx
        assert "Dave" in ctx
    finally:
        await agen.aclose()


async def test_cross_org_isolation_in_patterns(client):
    """Patterns from org 1 should not leak into org 2's context."""
    await _seed(1)
    await _seed(2)
    session, agen = await _get_db_session()
    try:
        emp = Employee(organization_id=1, name="OrgOneOnly", email="o1@test.com", is_active=True)
        session.add(emp)
        await session.flush()

        monday = _monday_of(date.today())
        session.add(TaskMetricWeekly(
            organization_id=1, employee_id=emp.id, week_start_date=monday,
            tasks_assigned=10, tasks_completed=10, on_time_rate=1.0,
        ))
        await session.commit()

        result_org1 = await build_work_patterns_context(session, org_id=1, weeks=2)
        result_org2 = await build_work_patterns_context(session, org_id=2, weeks=2)
        assert "OrgOneOnly" in result_org1
        assert "OrgOneOnly" not in result_org2
    finally:
        await agen.aclose()
