"""Schemas for SharePacket CRUD."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ShareContentType = Literal["memory", "context", "insight", "task"]
ShareStatus = Literal["proposed", "approved", "rejected", "applied"]


class SharePacketCreate(BaseModel):
    source_workspace_id: int
    target_workspace_id: int
    content_type: ShareContentType = "memory"
    title: str = Field(min_length=1, max_length=200)
    payload: str = Field(min_length=1, max_length=10000)


class SharePacketDecide(BaseModel):
    status: Literal["approved", "rejected"]
    decision_note: str | None = Field(default=None, max_length=500)


class SharePacketRead(BaseModel):
    id: int
    organization_id: int
    source_workspace_id: int
    target_workspace_id: int
    content_type: str
    title: str
    payload: str
    status: str
    proposed_by: int | None
    decided_by: int | None
    decision_note: str | None
    created_at: datetime
    decided_at: datetime | None

    model_config = {"from_attributes": True}
