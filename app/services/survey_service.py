"""Survey definition and response service — CRM module.

All business logic for surveys and responses. Organization-scoped; emits signals for audit.
"""

import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.survey import SurveyDefinition, SurveyResponse
from app.platform.signals import (
    SURVEY_DEFINITION_CREATED,
    SURVEY_RESPONSE_SUBMITTED,
    SignalCategory,
    SignalEnvelope,
    publish_signal,
)
from app.schemas.survey import SurveyDefinitionCreate, SurveyDefinitionUpdate, SurveyResponseCreate

logger = logging.getLogger(__name__)

_PROTECTED_DEFINITION_FIELDS = frozenset({"id", "organization_id", "total_responses", "created_at"})
_DEFINITION_UPDATE_FIELDS = frozenset({"title", "description", "questions_json", "is_active", "updated_at"})


async def _emit_survey_signal(
    db: AsyncSession | None,
    topic: str,
    organization_id: int,
    *,
    entity_type: str,
    entity_id: str,
    payload: dict,
    actor_user_id: int | None = None,
) -> None:
    try:
        await publish_signal(
            SignalEnvelope(
                topic=topic,
                category=SignalCategory.DOMAIN,
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                source="survey.service",
                entity_type=entity_type,
                entity_id=entity_id,
                payload=payload,
            ),
            db=db,
        )
    except Exception:
        logger.debug("Signal emission failed for %s entity=%s", topic, entity_id, exc_info=True)


async def get_survey_definition(
    db: AsyncSession,
    survey_id: int,
    organization_id: int,
) -> SurveyDefinition | None:
    result = await db.execute(
        select(SurveyDefinition).where(
            SurveyDefinition.id == survey_id,
            SurveyDefinition.organization_id == organization_id,
        )
    )
    return result.scalar_one_or_none()


async def list_survey_definitions(
    db: AsyncSession,
    organization_id: int,
    *,
    limit: int = 50,
    offset: int = 0,
    is_active: bool | None = None,
) -> list[SurveyDefinition]:
    query = select(SurveyDefinition).where(SurveyDefinition.organization_id == organization_id)
    if is_active is not None:
        query = query.where(SurveyDefinition.is_active.is_(is_active))
    query = query.order_by(SurveyDefinition.updated_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


async def create_survey_definition(
    db: AsyncSession,
    data: SurveyDefinitionCreate,
    organization_id: int,
) -> SurveyDefinition:
    definition = SurveyDefinition(
        organization_id=organization_id,
        title=data.title,
        description=data.description,
        questions_json=data.questions_json,
        is_active=data.is_active,
        total_responses=0,
    )
    db.add(definition)
    await db.commit()
    await db.refresh(definition)
    await _emit_survey_signal(
        db,
        SURVEY_DEFINITION_CREATED,
        organization_id,
        entity_type="survey_definition",
        entity_id=str(definition.id),
        payload={"survey_id": definition.id, "title": definition.title},
    )
    logger.info("survey definition created id=%d org=%d", definition.id, organization_id)
    return definition


async def update_survey_definition(
    db: AsyncSession,
    survey_id: int,
    data: SurveyDefinitionUpdate,
    organization_id: int,
) -> SurveyDefinition | None:
    definition = await get_survey_definition(db, survey_id, organization_id)
    if definition is None:
        return None
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        if key not in _PROTECTED_DEFINITION_FIELDS and key in _DEFINITION_UPDATE_FIELDS:
            setattr(definition, key, value)
    await db.commit()
    await db.refresh(definition)
    return definition


async def submit_response(
    db: AsyncSession,
    data: SurveyResponseCreate,
    organization_id: int,
    *,
    idempotency_key: str | None = None,
) -> SurveyResponse | None:
    definition = await get_survey_definition(db, data.survey_id, organization_id)
    if definition is None:
        return None
    if not definition.is_active:
        return None
    response = SurveyResponse(
        organization_id=organization_id,
        survey_id=data.survey_id,
        contact_id=data.contact_id,
        score=data.score,
        nps_score=data.nps_score,
        answers_json=data.answers_json,
        feedback=data.feedback,
    )
    db.add(response)
    await db.flush()
    definition.total_responses = (definition.total_responses or 0) + 1
    await db.commit()
    await db.refresh(response)
    await _emit_survey_signal(
        db,
        SURVEY_RESPONSE_SUBMITTED,
        organization_id,
        entity_type="survey_response",
        entity_id=str(response.id),
        payload={
            "response_id": response.id,
            "survey_id": response.survey_id,
            "score": response.score,
            "nps_score": response.nps_score,
            "idempotency_key": idempotency_key,
        },
    )
    logger.info("survey response submitted id=%d survey_id=%d org=%d", response.id, response.survey_id, organization_id)
    return response


async def get_response(
    db: AsyncSession,
    response_id: int,
    organization_id: int,
) -> SurveyResponse | None:
    result = await db.execute(
        select(SurveyResponse).where(
            SurveyResponse.id == response_id,
            SurveyResponse.organization_id == organization_id,
        )
    )
    return result.scalar_one_or_none()


async def list_responses(
    db: AsyncSession,
    survey_id: int,
    organization_id: int,
    *,
    limit: int = 100,
    offset: int = 0,
) -> list[SurveyResponse]:
    definition = await get_survey_definition(db, survey_id, organization_id)
    if definition is None:
        return []
    result = await db.execute(
        select(SurveyResponse)
        .where(
            SurveyResponse.survey_id == survey_id,
            SurveyResponse.organization_id == organization_id,
        )
        .order_by(SurveyResponse.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_aggregated_results(
    db: AsyncSession,
    survey_id: int,
    organization_id: int,
) -> dict:
    """Return aggregated survey results: avg score, NPS, response count, score distribution."""
    definition = await get_survey_definition(db, survey_id, organization_id)
    if definition is None:
        return {}
    result = await db.execute(
        select(
            func.count(SurveyResponse.id).label("count"),
            func.avg(SurveyResponse.score).label("avg_score"),
            func.avg(SurveyResponse.nps_score).label("avg_nps"),
        ).where(
            SurveyResponse.survey_id == survey_id,
            SurveyResponse.organization_id == organization_id,
        )
    )
    row = result.one()
    count = row.count or 0
    avg_score = float(row.avg_score) if row.avg_score is not None else None
    avg_nps = float(row.avg_nps) if row.avg_nps is not None else None
    score_buckets = {}
    if count > 0:
        bucket_result = await db.execute(
            select(SurveyResponse.score, func.count(SurveyResponse.id).label("n"))
            .where(
                SurveyResponse.survey_id == survey_id,
                SurveyResponse.organization_id == organization_id,
            )
            .group_by(SurveyResponse.score)
        )
        for score, n in bucket_result.all():
            score_buckets[int(score)] = n
    return {
        "survey_id": survey_id,
        "total_responses": count,
        "average_score": round(avg_score, 2) if avg_score is not None else None,
        "average_nps": round(avg_nps, 2) if avg_nps is not None else None,
        "score_distribution": score_buckets,
    }
