from datetime import datetime, date
from typing import Literal

from pydantic import BaseModel, Field

TaskCategory = Literal["personal", "business", "health", "finance", "other"]


class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    description: str | None = Field(None, max_length=2000)
    priority: int = Field(2, ge=1, le=4)  # 1=low  2=medium  3=high  4=urgent
    category: TaskCategory = "personal"
    project_id: int | None = None
    due_date: date | None = None


class TaskUpdate(BaseModel):
    is_done: bool


class TaskRead(BaseModel):
    id: int
    title: str
    description: str | None
    priority: int
    category: str
    project_id: int | None
    due_date: date | None
    is_done: bool
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}
