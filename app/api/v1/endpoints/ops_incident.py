from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.schemas.ops import (
    IncidentCommandRead,
    IncidentCommandTrendPointRead,
    IncidentCommandTrendRead,
)
from app.services import trend_telemetry

router = APIRouter(tags=["Ops"])


@router.get("/ops/incident/command-mode", response_model=IncidentCommandRead)
async def incident_command_mode(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> IncidentCommandRead:
    org_id = int(user["org_id"])
    payload_raw = await trend_telemetry.compute_incident_snapshot(db, org_id)
    payload = IncidentCommandRead.model_validate(payload_raw)
    await trend_telemetry.record_trend_event(
        db,
        org_id=org_id,
        event_type=trend_telemetry.INCIDENT_EVENT,
        payload_json={
            "incident_level": payload.incident_level,
            "score": int(payload.score),
        },
        actor_user_id=int(user["id"]),
        entity_type="ops_incident",
        throttle_minutes=15,
    )
    return payload


@router.get("/ops/incident/command-mode/trend", response_model=IncidentCommandTrendRead)
async def incident_command_mode_trend(
    limit: int = Query(14, ge=2, le=60),
    cursor: str | None = Query(None, max_length=128),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> IncidentCommandTrendRead:
    rows, next_cursor = await trend_telemetry.read_trend_events(
        db,
        org_id=int(user["org_id"]),
        event_type=trend_telemetry.INCIDENT_EVENT,
        limit=limit,
        cursor=cursor,
    )
    points: list[IncidentCommandTrendPointRead] = []
    for row in rows:
        payload = row.payload_json if isinstance(row.payload_json, dict) else {}
        level = str(payload.get("incident_level", "green")).lower()
        if level not in {"green", "amber", "red"}:
            level = "green"
        try:
            score = int(payload.get("score", 0))
        except (TypeError, ValueError):
            score = 0
        points.append(
            IncidentCommandTrendPointRead(
                timestamp=row.created_at,
                score=score,
                incident_level=level,  # type: ignore[arg-type]
            )
        )
    return IncidentCommandTrendRead(points=points, next_cursor=next_cursor)
