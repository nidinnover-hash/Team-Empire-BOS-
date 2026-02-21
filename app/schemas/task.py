from datetime import datetime, date
from pydantic import BaseModel


class TaskCreate(BaseModel):
    title: str
    description: str | None = None
    priority: int = 2          # 1=low  2=medium  3=high  4=urgent
    category: str = "personal" # personal | business | health | finance | other
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
