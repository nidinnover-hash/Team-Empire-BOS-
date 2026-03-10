"""Tests for quote_approval pending-only state guard."""
from __future__ import annotations

import pytest

from app.services import quote_approval as svc


@pytest.mark.asyncio
async def test_decide_pending_approval_succeeds(db):
    """A pending approval can be decided."""
    row = await svc.request_approval(
        db, organization_id=1, quote_id=10, approver_user_id=2,
        requested_by_user_id=1, level=1,
    )
    assert row.status == "pending"

    decided = await svc.decide(db, row.id, org_id=1, status="approved", reason="Looks good")
    assert decided is not None
    assert decided.status == "approved"
    assert decided.reason == "Looks good"
    assert decided.decided_at is not None


@pytest.mark.asyncio
async def test_decide_already_approved_returns_none(db):
    """An already-approved approval cannot be re-decided."""
    row = await svc.request_approval(
        db, organization_id=1, quote_id=11, approver_user_id=2,
        requested_by_user_id=1, level=1,
    )
    await svc.decide(db, row.id, org_id=1, status="approved", reason="First")

    second = await svc.decide(db, row.id, org_id=1, status="rejected", reason="Oops")
    assert second is None


@pytest.mark.asyncio
async def test_decide_already_rejected_returns_none(db):
    """An already-rejected approval cannot be re-decided."""
    row = await svc.request_approval(
        db, organization_id=1, quote_id=12, approver_user_id=2,
        requested_by_user_id=1, level=1,
    )
    await svc.decide(db, row.id, org_id=1, status="rejected", reason="No")

    second = await svc.decide(db, row.id, org_id=1, status="approved", reason="Changed mind")
    assert second is None


@pytest.mark.asyncio
async def test_decide_wrong_org_returns_none(db):
    """Approval from org1 cannot be decided by org2."""
    row = await svc.request_approval(
        db, organization_id=1, quote_id=13, approver_user_id=2,
        requested_by_user_id=1, level=1,
    )
    result = await svc.decide(db, row.id, org_id=2, status="approved")
    assert result is None


@pytest.mark.asyncio
async def test_decide_nonexistent_returns_none(db):
    """Non-existent approval ID returns None."""
    result = await svc.decide(db, 99999, org_id=1, status="approved")
    assert result is None
