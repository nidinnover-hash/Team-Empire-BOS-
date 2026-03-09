"""Approval workflow service — manage configurable approval chains."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.approval_workflow import ApprovalStep, ApprovalWorkflow


async def create_workflow(db: AsyncSession, organization_id: int, **kwargs) -> ApprovalWorkflow:
    wf = ApprovalWorkflow(organization_id=organization_id, **kwargs)
    db.add(wf)
    await db.commit()
    await db.refresh(wf)
    return wf


async def list_workflows(db: AsyncSession, organization_id: int, active_only: bool = True) -> list[ApprovalWorkflow]:
    q = select(ApprovalWorkflow).where(ApprovalWorkflow.organization_id == organization_id)
    if active_only:
        q = q.where(ApprovalWorkflow.is_active.is_(True))
    result = await db.execute(q.order_by(ApprovalWorkflow.id))
    return list(result.scalars().all())


async def delete_workflow(db: AsyncSession, workflow_id: int, organization_id: int) -> bool:
    result = await db.execute(
        select(ApprovalWorkflow).where(
            ApprovalWorkflow.id == workflow_id, ApprovalWorkflow.organization_id == organization_id,
        )
    )
    wf = result.scalar_one_or_none()
    if not wf:
        return False
    wf.is_active = False
    await db.commit()
    return True


async def add_step(db: AsyncSession, workflow_id: int, **kwargs) -> ApprovalStep:
    step = ApprovalStep(workflow_id=workflow_id, **kwargs)
    db.add(step)
    await db.commit()
    await db.refresh(step)
    return step


async def list_steps(db: AsyncSession, workflow_id: int) -> list[ApprovalStep]:
    result = await db.execute(
        select(ApprovalStep).where(ApprovalStep.workflow_id == workflow_id)
        .order_by(ApprovalStep.step_order)
    )
    return list(result.scalars().all())


async def get_workflow_with_steps(db: AsyncSession, workflow_id: int, organization_id: int) -> dict | None:
    result = await db.execute(
        select(ApprovalWorkflow).where(
            ApprovalWorkflow.id == workflow_id, ApprovalWorkflow.organization_id == organization_id,
        )
    )
    wf = result.scalar_one_or_none()
    if not wf:
        return None
    steps = await list_steps(db, workflow_id)
    return {
        "id": wf.id, "name": wf.name, "entity_type": wf.entity_type,
        "trigger_condition": wf.trigger_condition, "is_active": wf.is_active,
        "steps": [
            {"id": s.id, "step_order": s.step_order, "approver_role": s.approver_role,
             "approver_user_id": s.approver_user_id, "escalation_hours": s.escalation_hours}
            for s in steps
        ],
    }
