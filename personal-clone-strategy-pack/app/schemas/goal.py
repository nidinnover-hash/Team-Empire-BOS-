from datetime import datetime, date
from typing import Literal

from pydantic import BaseModel, Field

GoalStatus = Literal["active", "completed", "paused", "abandoned"]


class GoalCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(None, max_length=2000)
    category: str = Field("personal", max_length=50)  # personal | business | health | finance | learning | other
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
