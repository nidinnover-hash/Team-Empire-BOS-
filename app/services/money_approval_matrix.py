"""Money approval matrix — check if actor can auto-approve by role and amount band."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.money_approval_matrix import MoneyApprovalMatrix


async def can_auto_approve_money(
    db: AsyncSession,
    organization_id: int,
    *,
    action_type: str,
    amount: float,
    actor_role: str,
) -> bool:
    """
    True if the actor's role is in the matrix for this org/action_type/amount band.
    If no row matches, returns False (requires explicit approval).
    """
    result = await db.execute(
        select(MoneyApprovalMatrix)
        .where(
            MoneyApprovalMatrix.organization_id == organization_id,
            MoneyApprovalMatrix.action_type == action_type,
            MoneyApprovalMatrix.amount_min <= amount,
            MoneyApprovalMatrix.amount_max >= amount,
        )
    )
    row = result.scalar_one_or_none()
    if not row or not row.allowed_roles:
        return False
    roles = [r.upper() for r in row.allowed_roles if isinstance(r, str)]
    return (actor_role or "").upper() in roles
