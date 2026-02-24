from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

OrgRole = Literal[
    "OWNER",
    "ADMIN",
    "TECH_LEAD",
    "OPS_MANAGER",
    "DEVELOPER",
    "MANAGER",
    "STAFF",
    "VIEWER",
]


class OrganizationMembershipCreate(BaseModel):
    user_id: int = Field(..., ge=1)
    role: OrgRole = "VIEWER"


class OrganizationMembershipRead(BaseModel):
    id: int
    organization_id: int
    user_id: int
    role: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
