"""Tests for execution service tenant isolation: complete_execution must only update rows for the given org."""
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.models.approval import Approval
from app.models.execution import Execution
from app.services import execution as execution_service


async def _make_approval_and_execution(db, org_id: int, user_id: int = 1):
    """Create one Approval and one Execution for the given org; commit and return execution."""
    db.add(
        Approval(
            organization_id=org_id,
            requested_by=user_id,
            approval_type="workflow_step_execute",
            status="approved",
            approved_by=user_id,
            payload_json={},
        )
    )
    await db.commit()
    result = await db.execute(
        select(Approval).where(Approval.organization_id == org_id).order_by(Approval.id.desc()).limit(1)
    )
    approval = result.scalar_one()
    db.add(
        Execution(
            organization_id=org_id,
            approval_id=approval.id,
            triggered_by=user_id,
            status="running",
        )
    )
    await db.commit()
    result = await db.execute(
        select(Execution).where(Execution.organization_id == org_id).order_by(Execution.id.desc()).limit(1)
    )
    return result.scalar_one()


@pytest.mark.asyncio
async def test_complete_execution_with_correct_org_updates_row(db):
    """Complete execution with matching organization_id updates status and finished_at."""
    execution = await _make_approval_and_execution(db, 1)
    execution_id = execution.id
    assert execution.finished_at is None
    assert execution.status == "running"

    with patch("app.services.execution.publish_signal", new_callable=AsyncMock):
        out = await execution_service.complete_execution(
            db,
            execution_id,
            "succeeded",
            organization_id=1,
            output_json={"ok": True},
        )

    assert out is not None
    assert out.status == "succeeded"
    assert out.finished_at is not None
    await db.refresh(execution)
    assert execution.status == "succeeded"
    assert execution.finished_at is not None


@pytest.mark.asyncio
async def test_complete_execution_with_wrong_org_returns_none_and_does_not_update(db):
    """Complete execution with a different organization_id returns None and leaves row unchanged."""
    execution = await _make_approval_and_execution(db, 1)
    execution_id = execution.id

    out = await execution_service.complete_execution(
        db,
        execution_id,
        "succeeded",
        organization_id=2,
        output_json={"ok": True},
    )

    assert out is None
    await db.refresh(execution)
    assert execution.status == "running"
    assert execution.finished_at is None
