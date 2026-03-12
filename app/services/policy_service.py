"""
Decision log + policy engine.

- Stores decisions in the 5-block format
- Generates draft policy rules from decision patterns
- Policies are inactive by default (require explicit activation)
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.decision_log import DecisionLog
from app.models.policy_rule import PolicyRule
from app.schemas.ops import DecisionLogCreate

logger = logging.getLogger(__name__)


def _policy_signature(title: str, rule_text: str) -> str:
    def normalize(value: str) -> str:
        return re.sub(r"\s+", " ", (value or "").strip().lower())
    return f"{normalize(title)}::{normalize(rule_text)}"


# ---------------------------------------------------------------------------
# Decision Log CRUD
# ---------------------------------------------------------------------------

async def create_decision(
    db: AsyncSession,
    org_id: int,
    user_id: int,
    data: DecisionLogCreate,
) -> DecisionLog:
    entry = DecisionLog(
        organization_id=org_id,
        decision_type=data.decision_type,
        context=data.context,
        objective=data.objective,
        constraints=data.constraints,
        deadline=data.deadline,
        success_metric=data.success_metric,
        reason=data.reason,
        risk=data.risk,
        created_by=user_id,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


async def list_decisions(
    db: AsyncSession,
    org_id: int,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = 50,
) -> list[DecisionLog]:
    # Defense in depth: keep this service bounded even if callers bypass API validation.
    limit = max(1, min(int(limit or 50), 2000))
    query = select(DecisionLog).where(
        DecisionLog.organization_id == org_id,
    ).order_by(DecisionLog.created_at.desc()).limit(limit)

    if start_date:
        query = query.where(DecisionLog.created_at >= str(start_date))
    if end_date:
        query = query.where(DecisionLog.created_at < str(end_date))

    result = await db.execute(query)
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Policy Rule CRUD
# ---------------------------------------------------------------------------

async def list_policies(
    db: AsyncSession,
    org_id: int,
    active_only: bool = False,
) -> list[PolicyRule]:
    query = select(PolicyRule).where(PolicyRule.organization_id == org_id)
    if active_only:
        query = query.where(PolicyRule.is_active.is_(True))
    query = query.order_by(PolicyRule.created_at.desc()).limit(500)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_policy(db: AsyncSession, org_id: int, policy_id: int) -> PolicyRule | None:
    result = await db.execute(
        select(PolicyRule).where(
            PolicyRule.organization_id == org_id,
            PolicyRule.id == policy_id,
        )
    )
    return result.scalar_one_or_none()


async def activate_policy(db: AsyncSession, org_id: int, policy_id: int) -> PolicyRule | None:
    policy = await get_policy(db, org_id, policy_id)
    if policy is None:
        return None
    policy.is_active = True
    await db.commit()
    await db.refresh(policy)
    return policy


async def deactivate_policy(db: AsyncSession, org_id: int, policy_id: int) -> PolicyRule | None:
    policy = await get_policy(db, org_id, policy_id)
    if policy is None:
        return None
    policy.is_active = False
    await db.commit()
    await db.refresh(policy)
    return policy


# ---------------------------------------------------------------------------
# Policy generation (draft only)
# ---------------------------------------------------------------------------

async def generate_policy_drafts(
    db: AsyncSession,
    org_id: int,
) -> list[PolicyRule]:
    """
    Analyze recent decisions and generate draft policy rules.
    All generated policies are INACTIVE (is_active=False).
    Returns list of newly created draft policies.
    """
    decisions = await list_decisions(db, org_id, limit=100)
    if not decisions:
        return []

    # Group decisions by type
    by_type: dict[str, list[DecisionLog]] = {}
    for dec in decisions:
        by_type.setdefault(dec.decision_type, []).append(dec)

    drafts: list[PolicyRule] = []
    existing = await list_policies(db, org_id, active_only=False)
    signatures: set[str] = {
        _policy_signature(p.title, p.rule_text)
        for p in existing
    }

    def _maybe_add_policy(policy: PolicyRule) -> None:
        sig = _policy_signature(policy.title, policy.rule_text)
        if sig in signatures:
            return
        signatures.add(sig)
        db.add(policy)
        drafts.append(policy)

    # Pattern: repeated approvals with similar context → suggest policy
    approvals = by_type.get("approve", [])
    if len(approvals) >= 3:
        examples = [
            {"context": a.context[:200], "reason": a.reason[:200]}
            for a in approvals[:5]
        ]
        policy = PolicyRule(
            organization_id=org_id,
            title="Auto-approve pattern (from approval history)",
            rule_text=(
                f"Based on {len(approvals)} approval decisions, consider auto-approving "
                f"requests that match these patterns. Review each case individually."
            ),
            examples_json=json.dumps(examples),
            is_active=False,
        )
        _maybe_add_policy(policy)

    # Pattern: repeated rejections → suggest blocklist policy
    rejections = by_type.get("reject", [])
    if len(rejections) >= 2:
        examples = [
            {"context": r.context[:200], "reason": r.reason[:200]}
            for r in rejections[:5]
        ]
        policy = PolicyRule(
            organization_id=org_id,
            title="Rejection pattern (from rejection history)",
            rule_text=(
                f"Based on {len(rejections)} rejection decisions, consider blocking "
                f"requests that match these patterns upfront."
            ),
            examples_json=json.dumps(examples),
            is_active=False,
        )
        _maybe_add_policy(policy)

    # Pattern: deferred decisions → suggest escalation policy
    deferred = by_type.get("defer", [])
    if len(deferred) >= 2:
        examples = [
            {"context": d.context[:200], "reason": d.reason[:200]}
            for d in deferred[:5]
        ]
        policy = PolicyRule(
            organization_id=org_id,
            title="Deferral pattern (requires more data)",
            rule_text=(
                f"Based on {len(deferred)} deferred decisions, these request types "
                f"need additional data before a decision can be made. Consider requiring "
                f"supporting evidence upfront."
            ),
            examples_json=json.dumps(examples),
            is_active=False,
        )
        _maybe_add_policy(policy)

    if drafts:
        await db.commit()
        for d in drafts:
            await db.refresh(d)

    return drafts
