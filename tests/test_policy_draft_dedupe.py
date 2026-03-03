from sqlalchemy import select

from app.core.deps import get_db
from app.main import app as fastapi_app
from app.models.decision_log import DecisionLog
from app.models.policy_rule import PolicyRule
from app.services import policy_service


async def _get_session():
    override = fastapi_app.dependency_overrides[get_db]
    agen = override()
    session = await agen.__anext__()
    return session, agen


async def test_generate_policy_drafts_is_deduplicated(client):
    session, agen = await _get_session()
    try:
        for idx in range(3):
            session.add(
                DecisionLog(
                    organization_id=1,
                    decision_type="approve",
                    context=f"approve path {idx}",
                    objective="ship fast",
                    constraints="budget",
                    deadline=None,
                    success_metric="delivery",
                    reason="safe repeat",
                    risk="low",
                    created_by=1,
                )
            )
        await session.commit()

        first = await policy_service.generate_policy_drafts(session, org_id=1)
        second = await policy_service.generate_policy_drafts(session, org_id=1)
        assert len(first) >= 1
        assert len(second) == 0

        total = (
            await session.execute(
                select(PolicyRule).where(PolicyRule.organization_id == 1)
            )
        ).scalars().all()
        titles = [row.title for row in total]
        assert titles.count("Auto-approve pattern (from approval history)") == 1
    finally:
        await agen.aclose()
