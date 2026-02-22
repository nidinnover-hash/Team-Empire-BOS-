from datetime import datetime

from pydantic import BaseModel, Field


class EventCreate(BaseModel):
    organization_id: int = 1
    event_type: str
    actor_user_id: int | None = None
    entity_type: str | None = None
    entity_id: int | None = None
    payload_json: dict = Field(default_factory=dict)


class EventRead(BaseModel):
    id: int
    organization_id: int
    event_type: str
    actor_user_id: int | None
    entity_type: str | None
    entity_id: int | None
    payload_json: dict
    created_at: datetime

    model_config = {"from_attributes": True}
