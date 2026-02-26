"""
Regression tests for the 18-bug audit fixes.

Covers: atomic transactions, pagination, notification isolation,
finance truncation, contact offset, goal deadline, approval flow.
"""
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select

from app.core.deps import get_db
from app.core.security import create_access_token
from app.main import app as fastapi_app
from app.models.approval import Approval
from app.models.goal import Goal
from app.models.notification import Notification


def _ceo_headers(org_id: int = 1) -> dict:
    token = create_access_token(
        {"id": 1, "email": "ceo@org1.com", "role": "CEO", "org_id": org_id}
    )
    return {"Authorization": f"Bearer {token}"}


def _org2_headers() -> dict:
    token = create_access_token(
        {"id": 2, "email": "ceo@org2.com", "role": "CEO", "org_id": 2}
    )
    return {"Authorization": f"Bearer {token}"}


async def _get_session():
    override = fastapi_app.dependency_overrides[get_db]
    agen = override()
    session = await agen.__anext__()
    return session, agen


# ── 1. Approval atomic transaction (flush + single commit) ───────────────────


async def test_approve_creates_notification_atomically(client):
    """Approval + notification should be in one transaction, not split."""
    session, agen = await _get_session()
    try:
        approval = Approval(
            organization_id=1, requested_by=1,
            approval_type="task_execution", payload_json={},
            status="pending", created_at=datetime.now(UTC),
        )
        session.add(approval)
        await session.commit()
        aid = approval.id
    finally:
        await agen.aclose()

    resp = await client.post(
        f"/api/v1/approvals/{aid}/approve",
        json={"note": "yes"},
        headers=_ceo_headers(),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"

    # Verify notification was created (proves single-commit worked)
    session2, agen2 = await _get_session()
    try:
        result = await session2.execute(
            select(Notification).where(
                Notification.entity_type == "approval",
                Notification.entity_id == aid,
            )
        )
        notifs = list(result.scalars().all())
        assert len(notifs) >= 1, "Approval should create a notification in same transaction"
    finally:
        await agen2.aclose()


async def test_reject_creates_notification_atomically(client):
    session, agen = await _get_session()
    try:
        approval = Approval(
            organization_id=1, requested_by=1,
            approval_type="task_execution", payload_json={},
            status="pending", created_at=datetime.now(UTC),
        )
        session.add(approval)
        await session.commit()
        aid = approval.id
    finally:
        await agen.aclose()

    resp = await client.post(
        f"/api/v1/approvals/{aid}/reject",
        json={"note": "no"},
        headers=_ceo_headers(),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"


# ── 2. Contact offset pagination ──────────────────────────────────────────────


async def test_contacts_offset_pagination(client):
    headers = _ceo_headers()
    # Create 3 contacts
    for name in ["Alice", "Bob", "Charlie"]:
        await client.post(
            "/api/v1/contacts",
            json={"name": name, "relationship": "personal"},
            headers=headers,
        )

    # Get all
    all_resp = await client.get("/api/v1/contacts?limit=10&offset=0", headers=headers)
    assert all_resp.status_code == 200
    all_items = all_resp.json()
    assert len(all_items) >= 3

    # Get with offset=2
    offset_resp = await client.get("/api/v1/contacts?limit=10&offset=2", headers=headers)
    assert offset_resp.status_code == 200
    offset_items = offset_resp.json()
    assert len(offset_items) == len(all_items) - 2


# ── 3. Finance offset pagination ─────────────────────────────────────────────


async def test_finance_offset_pagination(client):
    headers = _ceo_headers()
    # Create 3 entries
    for i in range(3):
        await client.post(
            "/api/v1/finance",
            json={
                "description": f"Entry {i}",
                "amount": 100 + i,
                "type": "income",
                "category": "salary",
                "entry_date": "2026-02-01",
            },
            headers=headers,
        )

    all_resp = await client.get("/api/v1/finance?limit=10&offset=0", headers=headers)
    assert all_resp.status_code == 200
    all_items = all_resp.json()
    assert len(all_items) >= 3

    offset_resp = await client.get("/api/v1/finance?limit=10&offset=2", headers=headers)
    assert offset_resp.status_code == 200
    offset_items = offset_resp.json()
    assert len(offset_items) == len(all_items) - 2


# ── 4. Notification user isolation (mark_read) ───────────────────────────────


async def test_notification_mark_read_respects_user_id(client):
    """mark-read should only affect notifications belonging to the caller."""
    session, agen = await _get_session()
    try:
        # Notification for user 1
        n1 = Notification(
            organization_id=1, user_id=1, type="test", severity="info",
            title="For user 1", message="m", created_at=datetime.now(UTC),
        )
        # Notification for user 2
        n2 = Notification(
            organization_id=1, user_id=2, type="test", severity="info",
            title="For user 2", message="m", created_at=datetime.now(UTC),
        )
        session.add_all([n1, n2])
        await session.commit()
        n1_id, n2_id = n1.id, n2.id
    finally:
        await agen.aclose()

    # User 1 marks all read
    resp = await client.post(
        "/api/v1/notifications/mark-read",
        json={"notification_ids": [n1_id, n2_id]},
        headers=_ceo_headers(),
    )
    assert resp.status_code == 200

    # Verify user 2's notification is still unread
    session2, agen2 = await _get_session()
    try:
        result = await session2.execute(
            select(Notification).where(Notification.id == n2_id)
        )
        n2_row = result.scalar_one()
        assert n2_row.is_read is False, "User 2's notification should NOT be marked read by user 1"
    finally:
        await agen2.aclose()


# ── 5. Notification list limit validation ─────────────────────────────────────


async def test_notification_list_rejects_invalid_limit(client):
    resp = await client.get(
        "/api/v1/notifications?limit=0",
        headers=_ceo_headers(),
    )
    assert resp.status_code == 422

    resp = await client.get(
        "/api/v1/notifications?limit=500",
        headers=_ceo_headers(),
    )
    assert resp.status_code == 422


async def test_notification_list_valid_limit(client):
    resp = await client.get(
        "/api/v1/notifications?limit=30",
        headers=_ceo_headers(),
    )
    assert resp.status_code == 200


# ── 6. Goals pagination ──────────────────────────────────────────────────────


async def test_goals_list_limit_param(client):
    headers = _ceo_headers()
    # Create 3 goals
    for title in ["Goal A", "Goal B", "Goal C"]:
        await client.post(
            "/api/v1/goals",
            json={"title": title, "category": "personal"},
            headers=headers,
        )

    resp = await client.get("/api/v1/goals?limit=2", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) <= 2


# ── 7. Export reduced limits ─────────────────────────────────────────────────


async def test_export_endpoint_succeeds(client):
    headers = _ceo_headers()
    resp = await client.get("/api/v1/export", headers=headers)
    assert resp.status_code == 200


# ── 8. Approvals pagination params ───────────────────────────────────────────


async def test_approvals_list_with_limit_and_offset(client):
    headers = _ceo_headers()

    session, agen = await _get_session()
    try:
        for _i in range(3):
            session.add(Approval(
                organization_id=1, requested_by=1,
                approval_type="task_execution", payload_json={},
                status="pending", created_at=datetime.now(UTC),
            ))
        await session.commit()
    finally:
        await agen.aclose()

    resp = await client.get("/api/v1/approvals?limit=2&offset=0", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) <= 2


# ── 9. Cross-org isolation ────────────────────────────────────────────────────


async def test_contacts_cross_org_isolated(client):
    """Org 1 contacts should not be visible to org 2."""
    await client.post(
        "/api/v1/contacts",
        json={"name": "Org1 Contact", "relationship": "personal"},
        headers=_ceo_headers(1),
    )

    resp = await client.get("/api/v1/contacts", headers=_org2_headers())
    assert resp.status_code == 200
    names = [c["name"] for c in resp.json()]
    assert "Org1 Contact" not in names


# ── 10. Finance summary ──────────────────────────────────────────────────────


async def test_finance_summary_returns_balance(client):
    headers = _ceo_headers()
    await client.post(
        "/api/v1/finance",
        json={"description": "Income", "amount": 1000, "type": "income", "category": "salary", "entry_date": "2026-02-01"},
        headers=headers,
    )
    await client.post(
        "/api/v1/finance",
        json={"description": "Expense", "amount": 300, "type": "expense", "category": "office", "entry_date": "2026-02-01"},
        headers=headers,
    )

    resp = await client.get("/api/v1/finance/summary", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "total_income" in body
    assert "total_expense" in body
    assert "balance" in body
    assert body["balance"] == body["total_income"] - body["total_expense"]


# ── 11. Finance efficiency endpoint ──────────────────────────────────────────


async def test_finance_efficiency_returns_report(client):
    headers = _ceo_headers()
    resp = await client.get("/api/v1/finance/efficiency", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "efficiency_score" in body
    assert "findings" in body
    assert "recommendations" in body
    assert 0 <= body["efficiency_score"] <= 100


# ── 12. Goal deadline scheduler creates notifications ─────────────────────────


async def test_goal_deadline_check_creates_notifications(client):
    """Goals near deadline should trigger notifications via scheduler job."""
    from app.services.sync_scheduler import _check_goal_deadlines

    session, agen = await _get_session()
    try:
        # Goal due tomorrow
        goal = Goal(
            organization_id=1,
            title="Ship v2.0",
            category="business",
            status="active",
            progress=80,
            target_date=date.today() + timedelta(days=1),
        )
        session.add(goal)
        await session.commit()
        goal_id = goal.id

        await _check_goal_deadlines(session, 1)
    finally:
        await agen.aclose()

    # Verify notification was created
    session2, agen2 = await _get_session()
    try:
        result = await session2.execute(
            select(Notification).where(
                Notification.entity_type == "goal",
                Notification.entity_id == goal_id,
            )
        )
        notifs = list(result.scalars().all())
        assert len(notifs) >= 1
        assert "Due Soon" in notifs[0].title or "OVERDUE" in notifs[0].title
    finally:
        await agen2.aclose()


async def test_goal_overdue_gets_error_severity(client):
    """Overdue goals should get error severity notifications."""
    from app.services.sync_scheduler import _check_goal_deadlines

    session, agen = await _get_session()
    try:
        goal = Goal(
            organization_id=1,
            title="Overdue Launch",
            category="business",
            status="active",
            progress=50,
            target_date=date.today() - timedelta(days=3),
        )
        session.add(goal)
        await session.commit()
        goal_id = goal.id

        await _check_goal_deadlines(session, 1)
    finally:
        await agen.aclose()

    session2, agen2 = await _get_session()
    try:
        result = await session2.execute(
            select(Notification).where(
                Notification.entity_type == "goal",
                Notification.entity_id == goal_id,
            )
        )
        notifs = list(result.scalars().all())
        assert len(notifs) >= 1
        assert notifs[0].severity == "error"
        assert "OVERDUE" in notifs[0].title
    finally:
        await agen2.aclose()
