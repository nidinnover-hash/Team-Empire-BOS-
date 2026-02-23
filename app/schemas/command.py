from datetime import datetime

from pydantic import BaseModel, Field


class CommandCreate(BaseModel):
    command_text: str = Field(..., min_length=1, max_length=5000)
    ai_response: str | None = Field(None, max_length=10000)  # leave None to auto-call AI


class CommandRead(BaseModel):
    id: int
    command_text: str
    ai_response: str | None
    model_used: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
