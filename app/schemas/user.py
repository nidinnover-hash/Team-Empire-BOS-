from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    organization_id: int = 1
    name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: Literal[
        "CEO",
        "ADMIN",
        "MANAGER",
        "STAFF",
        "OWNER",
        "TECH_LEAD",
        "OPS_MANAGER",
        "DEVELOPER",
        "VIEWER",
    ] = "STAFF"


class UserRead(BaseModel):
    id: int
    organization_id: int
    name: str
    email: str
    role: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
