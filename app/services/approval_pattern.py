from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.approval_pattern import ApprovalPattern


@dataclass
class _ApprovalPatternRecord:
    id: int
    approval_type: str
    sample_payload: dict[str, Any] = field(default_factory=dict)
    approved_count: int = 0
    rejected_count: int = 0
    is_auto_approve_enabled: bool = False
    auto_approve_threshold: float = 0.9


async def should_auto_approve(
    db: AsyncSession,
    organization_id: int,
    approval_type: str,
    payload_json: dict[str, Any] | None = None,
) -> tuple[bool, float]:
    """Return (should_auto, confidence_score).

    Auto approval is allowed only if a pattern exists, auto-approve is enabled,
    and the approved_count has reached or exceeded the auto_approve_threshold.
    In all cases we also compute a confidence score based on the ratio of
    approved to total decisions.
    """
    stmt = select(ApprovalPattern).where(
        ApprovalPattern.organization_id == organization_id,
        ApprovalPattern.approval_type == approval_type,
    )
    result = await db.execute(stmt)
    pattern = result.scalar_one_or_none()
    if pattern is None:
        return False, 0.0
    record = _ApprovalPatternRecord(
        id=pattern.id,
        approval_type=pattern.approval_type,
        sample_payload=pattern.sample_payload or {},
        approved_count=pattern.approved_count or 0,
        rejected_count=pattern.rejected_count or 0,
        is_auto_approve_enabled=bool(pattern.is_auto_approve_enabled),
        auto_approve_threshold=float(pattern.auto_approve_threshold or 0.0),
    )
    conf = compute_confidence(record)
    if record.is_auto_approve_enabled and record.approved_count >= record.auto_approve_threshold:
        return True, conf
    return False, conf


async def get_or_create(
    db: AsyncSession,
    organization_id: int,
    approval_type: str,
    payload_json: dict[str, Any] | None = None,
) -> _ApprovalPatternRecord:
    stmt = select(ApprovalPattern).where(
        ApprovalPattern.organization_id == organization_id,
        ApprovalPattern.approval_type == approval_type,
    )
    result = await db.execute(stmt)
    pattern = result.scalar_one_or_none()
    if pattern is None:
        # create a new row
        pattern = ApprovalPattern(
            organization_id=organization_id,
            approval_type=approval_type,
            sample_payload=payload_json or {},
        )
        db.add(pattern)
        await db.commit()
        await db.refresh(pattern)
    return _ApprovalPatternRecord(
        id=pattern.id,
        approval_type=pattern.approval_type,
        sample_payload=pattern.sample_payload or {},
        approved_count=pattern.approved_count or 0,
        rejected_count=pattern.rejected_count or 0,
        is_auto_approve_enabled=bool(pattern.is_auto_approve_enabled),
        auto_approve_threshold=float(pattern.auto_approve_threshold or 0.0),
    )


async def record_decision(
    db: AsyncSession,
    pattern_id: int,
    *,
    approved: bool,
    decided_by_id: int,
) -> None:
    # pattern_id refers to existing row
    stmt = select(ApprovalPattern).where(ApprovalPattern.id == pattern_id)
    result = await db.execute(stmt)
    pattern = result.scalar_one_or_none()
    if pattern is None:
        return
    if approved:
        pattern.approved_count = (pattern.approved_count or 0) + 1
    else:
        pattern.rejected_count = (pattern.rejected_count or 0) + 1
    # do not update sample_payload here; it is set when pattern created
    await db.commit()


async def list_patterns(
    db: AsyncSession,
    *,
    organization_id: int,
) -> list[_ApprovalPatternRecord]:
    stmt = select(ApprovalPattern).where(
        ApprovalPattern.organization_id == organization_id
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()
    out: list[_ApprovalPatternRecord] = []
    for p in rows:
        out.append(
            _ApprovalPatternRecord(
                id=p.id,
                approval_type=p.approval_type,
                sample_payload=p.sample_payload or {},
                approved_count=p.approved_count or 0,
                rejected_count=p.rejected_count or 0,
                is_auto_approve_enabled=bool(p.is_auto_approve_enabled),
                auto_approve_threshold=float(p.auto_approve_threshold or 0.0),
            )
        )
    return out


async def update_pattern(
    db: AsyncSession,
    pattern_id: int,
    organization_id: int,
    is_auto_approve_enabled: bool | None,
    auto_approve_threshold: float | None,
) -> _ApprovalPatternRecord | None:
    stmt = select(ApprovalPattern).where(
        ApprovalPattern.id == pattern_id,
        ApprovalPattern.organization_id == organization_id,
    )
    result = await db.execute(stmt)
    pattern = result.scalar_one_or_none()
    if pattern is None:
        return None
    if is_auto_approve_enabled is not None:
        pattern.is_auto_approve_enabled = is_auto_approve_enabled
    if auto_approve_threshold is not None:
        pattern.auto_approve_threshold = auto_approve_threshold
    await db.commit()
    await db.refresh(pattern)
    return _ApprovalPatternRecord(
        id=pattern.id,
        approval_type=pattern.approval_type,
        sample_payload=pattern.sample_payload or {},
        approved_count=pattern.approved_count or 0,
        rejected_count=pattern.rejected_count or 0,
        is_auto_approve_enabled=bool(pattern.is_auto_approve_enabled),
        auto_approve_threshold=float(pattern.auto_approve_threshold or 0.0),
    )


async def delete_pattern(
    db: AsyncSession,
    pattern_id: int,
    organization_id: int,
) -> bool:
    stmt = delete(ApprovalPattern).where(
        ApprovalPattern.id == pattern_id,
        ApprovalPattern.organization_id == organization_id,
    )
    result = await db.execute(stmt)
    await db.commit()
    return bool(result.rowcount)


def compute_confidence(pattern: _ApprovalPatternRecord) -> float:
    total = max(0, int(pattern.approved_count) + int(pattern.rejected_count))
    if total == 0:
        return 0.0
    return round(float(pattern.approved_count) / float(total), 3)
