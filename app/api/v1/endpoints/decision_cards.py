"""Decision Cards — workspace-level human-in-the-loop decisions."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.logs.audit import record_action
from app.schemas.decision_card import (
    DecisionCardCreate,
    DecisionCardDecide,
    DecisionCardDefer,
    DecisionCardRead,
)
from app.services import decision_card as dc_service

router = APIRouter(prefix="/decision-cards", tags=["Decision Cards"])


@router.get("", response_model=list[DecisionCardRead])
async def list_decision_cards(
    workspace_id: int | None = Query(None),
    status: str | None = Query(None),
    urgency: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list[DecisionCardRead]:
    return await dc_service.list_decision_cards(
        db, org_id=int(user["org_id"]),
        workspace_id=workspace_id, status=status, urgency=urgency,
    )


@router.get("/pending-count")
async def get_pending_count(
    workspace_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> dict:
    count = await dc_service.get_pending_count(
        db, org_id=int(user["org_id"]), workspace_id=workspace_id,
    )
    return {"pending_count": count}


@router.get("/{card_id}", response_model=DecisionCardRead)
async def get_decision_card(
    card_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> DecisionCardRead:
    card = await dc_service.get_decision_card(db, org_id=int(user["org_id"]), card_id=card_id)
    if not card:
        raise HTTPException(status_code=404, detail="Decision card not found")
    return card


@router.post("", response_model=DecisionCardRead, status_code=201)
async def create_decision_card(
    data: DecisionCardCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> DecisionCardRead:
    org_id = int(user["org_id"])
    card = await dc_service.create_decision_card(
        db, org_id=org_id, data=data, proposed_by=int(user["id"]),
    )
    await record_action(
        db=db,
        event_type="decision_card_created",
        actor_user_id=int(user["id"]),
        entity_type="decision_card",
        entity_id=card.id,
        payload_json={"title": data.title, "urgency": data.urgency, "workspace_id": data.workspace_id},
        organization_id=org_id,
    )
    return card


@router.post("/{card_id}/decide", response_model=DecisionCardRead)
async def decide_card(
    card_id: int,
    decision: DecisionCardDecide,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> DecisionCardRead:
    org_id = int(user["org_id"])
    card = await dc_service.decide_card(
        db, org_id=org_id, card_id=card_id,
        decision=decision, decided_by=int(user["id"]),
    )
    if not card:
        raise HTTPException(status_code=404, detail="Decision card not found or already decided")
    await record_action(
        db=db,
        event_type="decision_card_decided",
        actor_user_id=int(user["id"]),
        entity_type="decision_card",
        entity_id=card.id,
        payload_json={"chosen_option": decision.chosen_option},
        organization_id=org_id,
    )
    return card


@router.post("/{card_id}/defer", response_model=DecisionCardRead)
async def defer_card(
    card_id: int,
    data: DecisionCardDefer,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> DecisionCardRead:
    org_id = int(user["org_id"])
    card = await dc_service.defer_card(
        db, org_id=org_id, card_id=card_id,
        rationale=data.decision_rationale, decided_by=int(user["id"]),
    )
    if not card:
        raise HTTPException(status_code=404, detail="Decision card not found or already decided")
    await record_action(
        db=db,
        event_type="decision_card_deferred",
        actor_user_id=int(user["id"]),
        entity_type="decision_card",
        entity_id=card.id,
        payload_json={"rationale": data.decision_rationale},
        organization_id=org_id,
    )
    return card
