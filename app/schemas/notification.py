from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class NotificationRead(BaseModel):
    id: int
    type: str
    severity: str
    title: str
    message: str
    source: str | None = None
    entity_type: str | None = None
    entity_id: int | None = None
    is_read: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class NotificationListRead(BaseModel):
    count: int
    unread_count: int
    items: list[NotificationRead]


class NotificationCountRead(BaseModel):
    unread_count: int


class NotificationMarkReadRequest(BaseModel):
    notification_ids: list[int] = Field(default_factory=list, max_length=100)


class NotificationMarkReadResponse(BaseModel):
    ok: bool
    marked_read: int
