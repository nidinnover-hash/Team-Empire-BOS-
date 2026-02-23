from datetime import datetime

from pydantic import BaseModel, Field


class NoteCreate(BaseModel):
    title: str | None = Field(None, max_length=255)
    content: str = Field(..., min_length=1, max_length=10000)
    tags: str | None = Field(None, max_length=500)  # comma-separated: "work,idea,urgent"


class NoteRead(BaseModel):
    id: int
    title: str | None
    content: str
    tags: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
