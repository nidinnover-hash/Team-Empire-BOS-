from datetime import datetime, date
from typing import Literal

from pydantic import BaseModel, Field

ProjectStatus = Literal["active", "completed", "paused", "archived"]
ProjectCategory = Literal["personal", "business", "health", "finance", "other"]


class ProjectCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(None, max_length=2000)
    category: ProjectCategory = "personal"
    due_date: date | None = None


class ProjectStatusUpdate(BaseModel):
    status: ProjectStatus


class ProjectRead(BaseModel):
    id: int
    title: str
    description: str | None
    category: str
    status: str
    due_date: date | None
    created_at: datetime

    model_config = {"from_attributes": True}
