"""CSAT survey service."""
from __future__ import annotations

import json

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.survey import SurveyDefinition, SurveyResponse


async def create_survey(
    db: AsyncSession, *, organization_id: int, title: str,
    description: str | None = None, questions: list[dict] | None = None,
    is_active: bool = True,
) -> SurveyDefinition:
    row = SurveyDefinition(
        organization_id=organization_id, title=title,
        description=description,
        questions_json=json.dumps(questions or []),
        is_active=is_active,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_surveys(
    db: AsyncSession, organization_id: int, *,
    is_active: bool | None = None,
) -> list[SurveyDefinition]:
    q = select(SurveyDefinition).where(SurveyDefinition.organization_id == organization_id)
    if is_active is not None:
        q = q.where(SurveyDefinition.is_active == is_active)
    q = q.order_by(SurveyDefinition.created_at.desc())
    return list((await db.execute(q)).scalars().all())


async def get_survey(db: AsyncSession, survey_id: int, organization_id: int) -> SurveyDefinition | None:
    q = select(SurveyDefinition).where(SurveyDefinition.id == survey_id, SurveyDefinition.organization_id == organization_id)
    return (await db.execute(q)).scalar_one_or_none()


async def update_survey(db: AsyncSession, survey_id: int, organization_id: int, **kwargs) -> SurveyDefinition | None:
    row = await get_survey(db, survey_id, organization_id)
    if not row:
        return None
    if "questions" in kwargs:
        kwargs["questions_json"] = json.dumps(kwargs.pop("questions") or [])
    for k, v in kwargs.items():
        if v is not None:
            setattr(row, k, v)
    await db.commit()
    await db.refresh(row)
    return row


async def delete_survey(db: AsyncSession, survey_id: int, organization_id: int) -> bool:
    row = await get_survey(db, survey_id, organization_id)
    if not row:
        return False
    await db.delete(row)
    await db.commit()
    return True


async def submit_response(
    db: AsyncSession, *, organization_id: int, survey_id: int,
    score: int = 0, nps_score: int | None = None,
    contact_id: int | None = None, answers: dict | None = None,
    feedback: str | None = None,
) -> SurveyResponse:
    resp = SurveyResponse(
        organization_id=organization_id, survey_id=survey_id,
        contact_id=contact_id, score=score, nps_score=nps_score,
        answers_json=json.dumps(answers or {}), feedback=feedback,
    )
    db.add(resp)
    survey = await get_survey(db, survey_id, organization_id)
    if survey:
        survey.total_responses += 1
    await db.commit()
    await db.refresh(resp)
    return resp


async def list_responses(
    db: AsyncSession, organization_id: int, survey_id: int,
    *, limit: int = 100,
) -> list[SurveyResponse]:
    q = (
        select(SurveyResponse)
        .where(SurveyResponse.organization_id == organization_id, SurveyResponse.survey_id == survey_id)
        .order_by(SurveyResponse.created_at.desc())
        .limit(limit)
    )
    return list((await db.execute(q)).scalars().all())


async def get_nps(db: AsyncSession, organization_id: int, survey_id: int) -> dict:
    rows = (await db.execute(
        select(SurveyResponse.nps_score)
        .where(SurveyResponse.organization_id == organization_id, SurveyResponse.survey_id == survey_id, SurveyResponse.nps_score.isnot(None))
    )).scalars().all()
    if not rows:
        return {"promoters": 0, "passives": 0, "detractors": 0, "nps": 0, "total": 0}
    promoters = sum(1 for s in rows if s >= 9)
    detractors = sum(1 for s in rows if s <= 6)
    passives = len(rows) - promoters - detractors
    nps = round((promoters - detractors) / len(rows) * 100, 1)
    return {"promoters": promoters, "passives": passives, "detractors": detractors, "nps": nps, "total": len(rows)}
