"""Service for cross-workspace Share Packets."""
import json
import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.share_packet import SharePacket
from app.schemas.share_packet import SharePacketCreate, SharePacketDecide

logger = logging.getLogger(__name__)


async def list_share_packets(
    db: AsyncSession,
    org_id: int,
    *,
    workspace_id: int | None = None,
    status: str | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list[SharePacket]:
    """List share packets for an org, optionally filtered by workspace or status."""
    query = (
        select(SharePacket)
        .where(SharePacket.organization_id == org_id)
        .order_by(SharePacket.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    if workspace_id is not None:
        query = query.where(
            (SharePacket.source_workspace_id == workspace_id)
            | (SharePacket.target_workspace_id == workspace_id)
        )
    if status:
        query = query.where(SharePacket.status == status)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_share_packet(
    db: AsyncSession, org_id: int, packet_id: int,
) -> SharePacket | None:
    result = await db.execute(
        select(SharePacket).where(
            SharePacket.id == packet_id,
            SharePacket.organization_id == org_id,
        )
    )
    return result.scalar_one_or_none()


async def create_share_packet(
    db: AsyncSession,
    org_id: int,
    data: SharePacketCreate,
    proposed_by: int,
) -> SharePacket:
    """Propose a new share packet."""
    packet = SharePacket(
        organization_id=org_id,
        source_workspace_id=data.source_workspace_id,
        target_workspace_id=data.target_workspace_id,
        content_type=data.content_type,
        title=data.title,
        payload=data.payload,
        status="proposed",
        proposed_by=proposed_by,
    )
    db.add(packet)
    await db.commit()
    await db.refresh(packet)
    return packet


async def decide_share_packet(
    db: AsyncSession,
    org_id: int,
    packet_id: int,
    decision: SharePacketDecide,
    decided_by: int,
) -> SharePacket | None:
    """Approve or reject a share packet."""
    packet = await get_share_packet(db, org_id, packet_id)
    if not packet:
        return None
    if packet.status != "proposed":
        return packet  # already decided
    packet.status = decision.status
    packet.decided_by = decided_by
    packet.decision_note = decision.decision_note
    packet.decided_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(packet)
    return packet


async def apply_share_packet(
    db: AsyncSession,
    org_id: int,
    packet_id: int,
) -> SharePacket | None:
    """Apply an approved share packet — copy content into target workspace.

    Supports content_type: memory, context, insight.
    """
    packet = await get_share_packet(db, org_id, packet_id)
    if not packet or packet.status != "approved":
        return None

    if packet.content_type == "memory":
        from app.services.memory import upsert_profile_memory
        try:
            data = json.loads(packet.payload)
        except (json.JSONDecodeError, TypeError):
            data = {"key": f"shared.{packet.id}", "value": packet.payload}
        await upsert_profile_memory(
            db,
            organization_id=org_id,
            key=data.get("key", f"shared.{packet.id}"),
            value=data.get("value", packet.payload),
            category=data.get("category", "shared"),
            workspace_id=packet.target_workspace_id,
        )
    elif packet.content_type == "context":
        from datetime import date

        from app.models.memory import DailyContext
        entry = DailyContext(
            organization_id=org_id,
            date=date.today(),
            context_type="decision",
            content=f"[Shared from WS#{packet.source_workspace_id}] {packet.payload}",
            workspace_id=packet.target_workspace_id,
            created_at=datetime.now(UTC),
        )
        db.add(entry)
    elif packet.content_type == "insight":
        from app.services.memory import upsert_profile_memory
        await upsert_profile_memory(
            db,
            organization_id=org_id,
            key=f"insight.shared.{packet.id}",
            value=packet.payload,
            category="insight",
            workspace_id=packet.target_workspace_id,
        )

    packet.status = "applied"
    await db.commit()
    await db.refresh(packet)
    logger.info(
        "Applied share packet %d: %s → ws#%d",
        packet.id, packet.content_type, packet.target_workspace_id,
    )
    return packet
