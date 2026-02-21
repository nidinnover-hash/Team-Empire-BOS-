from datetime import datetime
from pydantic import BaseModel


class CommandCreate(BaseModel):
    command_text: str
    ai_response: str | None = None  # leave None to auto-call OpenAI


class CommandRead(BaseModel):
    id: int
    command_text: str
    ai_response: str | None
    model_used: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
