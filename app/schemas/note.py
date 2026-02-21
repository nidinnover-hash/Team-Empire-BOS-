from datetime import datetime
from pydantic import BaseModel


class NoteCreate(BaseModel):
    title: str | None = None
    content: str
    tags: str | None = None  # comma-separated: "work,idea,urgent"


class NoteRead(BaseModel):
    id: int
    title: str | None
    content: str
    tags: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
