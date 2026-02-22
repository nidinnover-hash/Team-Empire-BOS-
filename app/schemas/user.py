from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    organization_id: int = 1
    name: str
    email: str
    password: str = Field(min_length=8)
    role: Literal["CEO", "ADMIN", "MANAGER", "STAFF"] = "STAFF"


class UserRead(BaseModel):
    id: int
    organization_id: int
    name: str
    email: str
    role: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
