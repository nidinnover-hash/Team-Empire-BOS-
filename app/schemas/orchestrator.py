"""Schemas for CEO Orchestrator — cross-workspace intelligence."""
from datetime import datetime

from pydantic import BaseModel


class WorkspaceHealth(BaseModel):
    workspace_id: int
    workspace_name: str
    workspace_type: str
    memory_count: int
    pending_decisions: int
    recent_tasks: int
    recent_share_packets: int
    health_score: float  # 0-100
    status: str  # healthy | attention | critical


class CrossWorkspacePattern(BaseModel):
    pattern_type: str  # overlap | gap | opportunity | conflict
    title: str
    description: str
    workspace_ids: list[int]
    suggested_action: str | None = None


class OrchestratorBriefing(BaseModel):
    organization_id: int
    total_workspaces: int
    active_workspaces: int
    total_pending_decisions: int
    total_pending_shares: int
    workspace_health: list[WorkspaceHealth]
    patterns: list[CrossWorkspacePattern]
    generated_at: datetime
