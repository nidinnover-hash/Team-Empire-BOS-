from datetime import datetime, date
from typing import Literal

from pydantic import BaseModel

ProjectStatus = Literal["active", "completed", "paused", "archived"]


class ProjectCreate(BaseModel):
    title: str
    description: str | None = None
    category: str = "personal"  # personal | business | health | finance | other
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
