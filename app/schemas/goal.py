from datetime import datetime, date
from typing import Literal

from pydantic import BaseModel, Field

GoalStatus = Literal["active", "completed", "paused", "abandoned"]


class GoalCreate(BaseModel):
    title: str
    description: str | None = None
    category: str = "personal"  # personal | business | health | finance | learning | other
    target_date: date | None = None


class GoalProgressUpdate(BaseModel):
    progress: int = Field(ge=0, le=100)  # 0–100, validated


class GoalStatusUpdate(BaseModel):
    status: GoalStatus


class GoalRead(BaseModel):
    id: int
    title: str
    description: str | None
    category: str
    target_date: date | None
    status: str
    progress: int
    created_at: datetime

    model_config = {"from_attributes": True}
