"""CEO Orchestrator — cross-workspace intelligence and health scoring."""
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.decision_card import DecisionCard
from app.models.memory import ProfileMemory
from app.models.share_packet import SharePacket
from app.models.task import Task
from app.models.workspace import Workspace
from app.schemas.orchestrator import (
    CrossWorkspacePattern,
    OrchestratorBriefing,
    WorkspaceHealth,
)

logger = logging.getLogger(__name__)


async def compute_workspace_health(
    db: AsyncSession, org_id: int, workspace: Workspace,
) -> WorkspaceHealth:
    """Compute health score for a single workspace brain."""
    ws_id = workspace.id
    now = datetime.now(UTC)
    week_ago = now - timedelta(days=7)

    # Memory density
    mem_count_result = await db.execute(
        select(func.count(ProfileMemory.id)).where(
            ProfileMemory.organization_id == org_id,
            ProfileMemory.workspace_id == ws_id,
        )
    )
    memory_count = mem_count_result.scalar() or 0

    # Pending decisions
    pending_result = await db.execute(
        select(func.count(DecisionCard.id)).where(
            DecisionCard.organization_id == org_id,
            DecisionCard.workspace_id == ws_id,
            DecisionCard.status == "pending",
        )
    )
    pending_decisions = pending_result.scalar() or 0

    # Recent tasks (last 7 days)
    task_result = await db.execute(
        select(func.count(Task.id)).where(
            Task.organization_id == org_id,
            Task.workspace_id == ws_id,
            Task.created_at >= week_ago,
        )
    )
    recent_tasks = task_result.scalar() or 0

    # Recent share packets involving this workspace
    share_result = await db.execute(
        select(func.count(SharePacket.id)).where(
            SharePacket.organization_id == org_id,
            (SharePacket.source_workspace_id == ws_id)
            | (SharePacket.target_workspace_id == ws_id),
            SharePacket.created_at >= week_ago,
        )
    )
    recent_shares = share_result.scalar() or 0

    # Health score: weighted combination
    # - Memory richness (0-30): more memory = healthier brain
    # - Decision velocity (0-30): fewer pending = better
    # - Activity (0-25): recent tasks = active brain
    # - Connectivity (0-15): share packets = connected brain
    mem_score = min(30, memory_count * 3)
    decision_score = max(0, 30 - pending_decisions * 6)
    activity_score = min(25, recent_tasks * 5)
    connect_score = min(15, recent_shares * 5)
    health_score = round(mem_score + decision_score + activity_score + connect_score, 1)

    if health_score >= 70:
        status = "healthy"
    elif health_score >= 40:
        status = "attention"
    else:
        status = "critical"

    return WorkspaceHealth(
        workspace_id=ws_id,
        workspace_name=workspace.name,
        workspace_type=workspace.workspace_type or "general",
        memory_count=memory_count,
        pending_decisions=pending_decisions,
        recent_tasks=recent_tasks,
        recent_share_packets=recent_shares,
        health_score=health_score,
        status=status,
    )


async def detect_cross_workspace_patterns(
    db: AsyncSession, org_id: int, workspaces: list[Workspace],
) -> list[CrossWorkspacePattern]:
    """Detect patterns across workspace brains."""
    patterns: list[CrossWorkspacePattern] = []
    if len(workspaces) < 2:
        return patterns

    ws_ids = [ws.id for ws in workspaces]
    ws_names = {ws.id: ws.name for ws in workspaces}

    # Pattern 1: Memory overlap — same keys in multiple workspaces
    mem_result = await db.execute(
        select(ProfileMemory.key, func.count(func.distinct(ProfileMemory.workspace_id)))
        .where(
            ProfileMemory.organization_id == org_id,
            ProfileMemory.workspace_id.in_(ws_ids),
        )
        .group_by(ProfileMemory.key)
        .having(func.count(func.distinct(ProfileMemory.workspace_id)) > 1)
    )
    overlapping_keys = list(mem_result.all())
    if overlapping_keys:
        keys_preview = ", ".join(row[0] for row in overlapping_keys[:5])
        patterns.append(CrossWorkspacePattern(
            pattern_type="overlap",
            title="Shared memory keys across workspaces",
            description=f"{len(overlapping_keys)} memory keys exist in multiple workspaces: {keys_preview}",
            workspace_ids=ws_ids,
            suggested_action="Review for consistency — different workspaces may have divergent values for the same key.",
        ))

    # Pattern 2: Isolated workspaces — no share packets in/out
    for ws in workspaces:
        share_count = await db.execute(
            select(func.count(SharePacket.id)).where(
                SharePacket.organization_id == org_id,
                (SharePacket.source_workspace_id == ws.id)
                | (SharePacket.target_workspace_id == ws.id),
            )
        )
        if (share_count.scalar() or 0) == 0:
            patterns.append(CrossWorkspacePattern(
                pattern_type="gap",
                title=f"'{ws_names[ws.id]}' is isolated",
                description=f"Workspace '{ws_names[ws.id]}' has never shared or received knowledge from other brains.",
                workspace_ids=[ws.id],
                suggested_action="Consider sharing key insights from this workspace to other brains.",
            ))

    # Pattern 3: Decision bottleneck — workspace with many pending decisions
    bottleneck_result = await db.execute(
        select(DecisionCard.workspace_id, func.count(DecisionCard.id))
        .where(
            DecisionCard.organization_id == org_id,
            DecisionCard.status == "pending",
        )
        .group_by(DecisionCard.workspace_id)
        .having(func.count(DecisionCard.id) >= 3)
    )
    for ws_id_val, count in bottleneck_result.all():
        name = ws_names.get(ws_id_val, f"WS#{ws_id_val}")
        patterns.append(CrossWorkspacePattern(
            pattern_type="opportunity",
            title=f"Decision bottleneck in '{name}'",
            description=f"'{name}' has {count} pending decisions awaiting human input.",
            workspace_ids=[ws_id_val],
            suggested_action="Review and resolve pending decisions to unblock this workspace brain.",
        ))

    return patterns


async def generate_briefing(
    db: AsyncSession, org_id: int,
) -> OrchestratorBriefing:
    """Generate a CEO-level briefing across all workspace brains."""
    # Fetch all active workspaces
    ws_result = await db.execute(
        select(Workspace).where(
            Workspace.organization_id == org_id,
            Workspace.is_active.is_(True),
        ).order_by(Workspace.is_default.desc(), Workspace.name)
    )
    workspaces = list(ws_result.scalars().all())

    # Compute health for each
    health_list = []
    for ws in workspaces:
        health = await compute_workspace_health(db, org_id, ws)
        health_list.append(health)

    # Detect patterns
    patterns = await detect_cross_workspace_patterns(db, org_id, workspaces)

    # Aggregate counts
    total_pending_decisions = sum(h.pending_decisions for h in health_list)

    pending_shares_result = await db.execute(
        select(func.count(SharePacket.id)).where(
            SharePacket.organization_id == org_id,
            SharePacket.status == "proposed",
        )
    )
    total_pending_shares = pending_shares_result.scalar() or 0

    return OrchestratorBriefing(
        organization_id=org_id,
        total_workspaces=len(workspaces),
        active_workspaces=len(workspaces),
        total_pending_decisions=total_pending_decisions,
        total_pending_shares=total_pending_shares,
        workspace_health=health_list,
        patterns=patterns,
        generated_at=datetime.now(UTC),
    )
