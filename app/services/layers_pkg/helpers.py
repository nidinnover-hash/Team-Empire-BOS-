"""Shared helpers for layer functions — query safety, aggregation, scoring."""
from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

logger = logging.getLogger(__name__)

# Type alias for penalty rules: (condition, deduction, risk_message, action_message)
PenaltyRule = tuple[Callable[[dict[str, Any]], bool], int, str, str]

# Risk-only rules (no score deduction) — used when scoring is index-based
RiskRule = tuple[Callable[[dict[str, Any]], bool], str, str]

# Shared keyword tuples used by multiple layer modules
MARKETING_TASK_KEYWORDS = ("lead", "follow", "campaign", "outreach", "marketing", "sales")


def contains_any(text: str | None, keywords: tuple[str, ...]) -> bool:
    """Check if any keyword appears in the lowered text."""
    t = (text or "").strip().lower()
    return any(k in t for k in keywords)


async def safe_query(db: AsyncSession, stmt: Select, label: str, org_id: int) -> list:
    """Execute a query with fallback to empty list on failure."""
    try:
        result = await db.execute(stmt)
        return list(result.scalars().all())
    except Exception:
        logger.warning("%s query failed org=%d", label, org_id, exc_info=True)
        return []


def latest_by_employee(rows: Sequence) -> dict[int, Any]:
    """Return the first (latest) row per employee_id from pre-sorted rows."""
    out: dict[int, Any] = {}
    for row in rows:
        if row.employee_id not in out:
            out[row.employee_id] = row
    return out


def apply_penalties(
    rules: list[PenaltyRule],
    ctx: dict[str, Any],
    default_action: str,
) -> tuple[int, list[str], list[str]]:
    """Apply penalty rules and return (score, risks, actions). Score starts at 100."""
    score = 100
    risks: list[str] = []
    actions: list[str] = []
    for condition, deduction, risk_msg, action_msg in rules:
        if condition(ctx):
            score -= deduction
            risks.append(risk_msg)
            actions.append(action_msg)
    if not actions:
        actions.append(default_action)
    return max(0, min(100, score)), risks[:4], actions[:4]


def apply_risk_rules(
    rules: list[RiskRule],
    ctx: dict[str, Any],
    default_action: str,
) -> tuple[list[str], list[str]]:
    """Apply risk-only rules (no score impact). Returns (risks, actions)."""
    risks: list[str] = []
    actions: list[str] = []
    for condition, risk_msg, action_msg in rules:
        if condition(ctx):
            risks.append(risk_msg)
            actions.append(action_msg)
    if not actions:
        actions.append(default_action)
    return risks[:4], actions[:4]


def avg_ai_level(members: Sequence, *, ai_attr: str = "ai_level") -> float:
    """Compute average AI level across members, defaulting missing to 0."""
    count = len(members)
    if not count:
        return 0.0
    return round(sum((getattr(m, ai_attr, None) or 0) for m in members) / count, 2)
