from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.logs.audit import record_action
from app.schemas.data_collection import (
    CloneProTrainingRequest,
    CloneProTrainingResult,
    DataCollectRequest,
    DataCollectResult,
)
from app.services import data_collection as data_collection_service

router = APIRouter(prefix="/data", tags=["Data Collection"])


@router.post("/collect", response_model=DataCollectResult)
async def collect_data(
    data: DataCollectRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> DataCollectResult:
    org_id = int(actor["org_id"])
    try:
        result = await data_collection_service.ingest_data(
            db=db,
            org_id=org_id,
            data=data,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await record_action(
        db=db,
        event_type="data_collected",
        actor_user_id=int(actor["id"]),
        organization_id=org_id,
        entity_type="data_ingest",
        entity_id=result.created_ids[0] if result.created_ids else None,
        payload_json={
            "source": data.source,
            "target": data.target,
            "count": result.ingested_count,
        },
    )
    return result


@router.post("/train-pro", response_model=CloneProTrainingResult)
async def train_clone_pro(
    data: CloneProTrainingRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> CloneProTrainingResult:
    org_id = int(actor["org_id"])
    try:
        result = await data_collection_service.train_clone_pro(
            db=db,
            org_id=org_id,
            data=data,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await record_action(
        db=db,
        event_type="clone_trained_pro",
        actor_user_id=int(actor["id"]),
        organization_id=org_id,
        entity_type="training",
        entity_id=None,
        payload_json={
            "source": data.source,
            "profile_memory_written": result.profile_memory_written,
            "daily_context_written": result.daily_context_written,
            "notes_written": result.notes_written,
        },
    )
    return result
