import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator


class UserCreate(BaseModel):
    organization_id: int
    name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def password_complexity(cls, v: str) -> str:
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        if not re.search(r"[^A-Za-z0-9]", v):
            raise ValueError("Password must contain at least one special character")
        return v
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


class RoleChangeRequest(BaseModel):
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
    ]


class UserToggleActive(BaseModel):
    is_active: bool


class UserRead(BaseModel):
    id: int
    organization_id: int
    name: str
    email: str
    role: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
