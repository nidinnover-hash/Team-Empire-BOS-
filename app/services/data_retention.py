"""Data retention policy service — CRUD and dry-run evaluation."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.data_retention import DataRetentionPolicy


async def create_policy(db: AsyncSession, organization_id: int, **kwargs) -> DataRetentionPolicy:
    policy = DataRetentionPolicy(organization_id=organization_id, **kwargs)
    db.add(policy)
    await db.commit()
    await db.refresh(policy)
    return policy


async def list_policies(
    db: AsyncSession, organization_id: int, active_only: bool = True,
) -> list[DataRetentionPolicy]:
    q = select(DataRetentionPolicy).where(DataRetentionPolicy.organization_id == organization_id)
    if active_only:
        q = q.where(DataRetentionPolicy.is_active.is_(True))
    result = await db.execute(q.order_by(DataRetentionPolicy.id))
    return list(result.scalars().all())


async def update_policy(
    db: AsyncSession, policy_id: int, organization_id: int, **kwargs,
) -> DataRetentionPolicy | None:
    result = await db.execute(
        select(DataRetentionPolicy).where(
            DataRetentionPolicy.id == policy_id,
            DataRetentionPolicy.organization_id == organization_id,
        )
    )
    policy = result.scalar_one_or_none()
    if not policy:
        return None
    for k, v in kwargs.items():
        if v is not None and hasattr(policy, k):
            setattr(policy, k, v)
    await db.commit()
    await db.refresh(policy)
    return policy


async def delete_policy(db: AsyncSession, policy_id: int, organization_id: int) -> bool:
    result = await db.execute(
        select(DataRetentionPolicy).where(
            DataRetentionPolicy.id == policy_id,
            DataRetentionPolicy.organization_id == organization_id,
        )
    )
    policy = result.scalar_one_or_none()
    if not policy:
        return False
    policy.is_active = False
    await db.commit()
    return True


async def evaluate_policy(
    db: AsyncSession, policy_id: int, organization_id: int,
) -> dict:
    """Dry-run: calculate how many records would be affected."""
    result = await db.execute(
        select(DataRetentionPolicy).where(
            DataRetentionPolicy.id == policy_id,
            DataRetentionPolicy.organization_id == organization_id,
        )
    )
    policy = result.scalar_one_or_none()
    if not policy:
        return {"error": "Policy not found"}
    cutoff = datetime.now(UTC) - timedelta(days=policy.retention_days)
    return {
        "policy_id": policy.id,
        "entity_type": policy.entity_type,
        "action": policy.action,
        "retention_days": policy.retention_days,
        "cutoff_date": cutoff.isoformat(),
        "dry_run": True,
        "estimated_records": 0,  # real count would query entity table
    }
