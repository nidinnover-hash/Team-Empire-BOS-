from __future__ import annotations

from datetime import date

import pytest


@pytest.mark.asyncio
async def test_build_brain_context_includes_employee_profile_and_patterns(db):
    from app.models.employee import Employee
    from app.models.employee_work_pattern import EmployeeWorkPattern
    from app.schemas.brain_context import BrainContext
    from app.services import clone_control
    from app.services.context_builder import build_brain_context

    emp = Employee(
        organization_id=1,
        name="Alice",
        role="Engineer",
        email="alice@org1.com",
        is_active=True,
    )
    db.add(emp)
    await db.commit()
    await db.refresh(emp)

    await clone_control.upsert_clone_profile(
        db,
        organization_id=1,
        employee_id=emp.id,
        strengths=["ownership", "communication"],
        weak_zones=["estimation"],
        preferred_task_types=["delivery"],
    )
    db.add(
        EmployeeWorkPattern(
            organization_id=1,
            employee_id=emp.id,
            work_date=date.today(),
            hours_logged=8.0,
            active_minutes=360,
            focus_minutes=210,
            meetings_minutes=90,
            tasks_completed=4,
            source="manual",
        )
    )
    await db.commit()

    ctx = await build_brain_context(
        db,
        organization_id=1,
        actor_user_id=1,
        actor_role="ADMIN",
        employee_id=emp.id,
        request_purpose="professional",
    )

    assert isinstance(ctx, BrainContext)
    assert ctx.organization_id == 1
    assert "employee:write" in ctx.capabilities
    assert ctx.employee is not None
    assert ctx.employee.employee_id == emp.id
    assert ctx.employee.profile.get("employee_id") == emp.id
    assert ctx.employee.recent_work_pattern.get("window_days") == 7


@pytest.mark.asyncio
async def test_build_brain_context_blocks_cross_org_employee(db):
    from app.models.employee import Employee
    from app.services.context_builder import build_brain_context

    foreign_emp = Employee(
        organization_id=2,
        name="Bob",
        role="Sales",
        email="bob@org2.com",
        is_active=True,
    )
    db.add(foreign_emp)
    await db.commit()
    await db.refresh(foreign_emp)

    ctx = await build_brain_context(
        db,
        organization_id=1,
        actor_user_id=1,
        actor_role="CEO",
        employee_id=foreign_emp.id,
    )
    assert ctx.organization_id == 1
    assert ctx.employee is None


@pytest.mark.asyncio
async def test_call_ai_uses_brain_context_org_and_injects_context(monkeypatch):
    from app.schemas.brain_context import BrainContext, OrgContext
    from app.services import ai_router

    captured: dict[str, object] = {}

    async def fake_call_provider(
        provider: str,
        system_prompt: str,
        user_message: str,
        max_tokens: int,
        conversation_history=None,
        org_id: int = 1,
    ):
        captured["provider"] = provider
        captured["system_prompt"] = system_prompt
        captured["org_id"] = org_id
        return "ok-response", False, 10, 5

    async def fake_log_ai_call(**_kwargs):
        return None

    monkeypatch.setattr(ai_router, "_call_provider", fake_call_provider)
    monkeypatch.setattr(ai_router, "_log_ai_call", fake_log_ai_call)
    ai_router.set_ai_key_cache("groq", "gsk-test-key", org_id=99)

    brain_context = BrainContext(
        organization_id=99,
        actor_user_id=7,
        actor_role="MANAGER",
        request_purpose="professional",
        capabilities=["org:read"],
        org=OrgContext(
            id=99,
            slug="org-99",
            name="Org 99",
            country_code="IN",
            branch_label="Bangalore",
            parent_organization_id=None,
            policy={"autonomy_policy": {"current_mode": "approved_execution"}},
        ),
        employee=None,
    )
    result = await ai_router.call_ai(
        system_prompt="System prompt.",
        user_message="Hello",
        provider="groq",
        brain_context=brain_context,
    )
    ai_router.clear_ai_key_cache("groq", org_id=99)

    assert result == "ok-response"
    assert captured["org_id"] == 99
    assert "[BRAIN CONTEXT - TENANT SCOPED]" in str(captured["system_prompt"])
    assert "organization_id=99" in str(captured["system_prompt"])
