"""Share Packets — cross-workspace knowledge transfer endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.logs.audit import record_action
from app.schemas.share_packet import SharePacketCreate, SharePacketDecide, SharePacketRead
from app.services import share_packet as sp_service

router = APIRouter(prefix="/share-packets", tags=["Share Packets"])


@router.get("", response_model=list[SharePacketRead])
async def list_share_packets(
    workspace_id: int | None = Query(None, description="Filter by workspace"),
    status: str | None = Query(None, description="Filter by status"),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list[SharePacketRead]:
    return await sp_service.list_share_packets(
        db, org_id=int(user["org_id"]),
        workspace_id=workspace_id, status=status,
    )


@router.get("/{packet_id}", response_model=SharePacketRead)
async def get_share_packet(
    packet_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> SharePacketRead:
    packet = await sp_service.get_share_packet(db, org_id=int(user["org_id"]), packet_id=packet_id)
    if not packet:
        raise HTTPException(status_code=404, detail="Share packet not found")
    return packet


@router.post("", response_model=SharePacketRead, status_code=201)
async def create_share_packet(
    data: SharePacketCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> SharePacketRead:
    if data.source_workspace_id == data.target_workspace_id:
        raise HTTPException(status_code=400, detail="Source and target must be different workspaces")
    org_id = int(user["org_id"])
    packet = await sp_service.create_share_packet(
        db, org_id=org_id, data=data, proposed_by=int(user["id"]),
    )
    await record_action(
        db=db,
        event_type="share_packet_proposed",
        actor_user_id=int(user["id"]),
        entity_type="share_packet",
        entity_id=packet.id,
        payload_json={"title": data.title, "content_type": data.content_type},
        organization_id=org_id,
    )
    return packet


@router.post("/{packet_id}/decide", response_model=SharePacketRead)
async def decide_share_packet(
    packet_id: int,
    decision: SharePacketDecide,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> SharePacketRead:
    org_id = int(user["org_id"])
    packet = await sp_service.decide_share_packet(
        db, org_id=org_id, packet_id=packet_id,
        decision=decision, decided_by=int(user["id"]),
    )
    if not packet:
        raise HTTPException(status_code=404, detail="Share packet not found")
    await record_action(
        db=db,
        event_type=f"share_packet_{decision.status}",
        actor_user_id=int(user["id"]),
        entity_type="share_packet",
        entity_id=packet.id,
        payload_json={"status": decision.status, "note": decision.decision_note},
        organization_id=org_id,
    )
    return packet


@router.post("/{packet_id}/apply", response_model=SharePacketRead)
async def apply_share_packet(
    packet_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> SharePacketRead:
    org_id = int(user["org_id"])
    packet = await sp_service.apply_share_packet(db, org_id=org_id, packet_id=packet_id)
    if not packet:
        raise HTTPException(status_code=404, detail="Share packet not found or not approved")
    await record_action(
        db=db,
        event_type="share_packet_applied",
        actor_user_id=int(user["id"]),
        entity_type="share_packet",
        entity_id=packet.id,
        payload_json={"content_type": packet.content_type},
        organization_id=org_id,
    )
    return packet
