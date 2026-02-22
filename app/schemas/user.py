from datetime import datetime

from pydantic import BaseModel


class UserCreate(BaseModel):
    organization_id: int = 1
    name: str
    email: str
    password: str
    role: str = "STAFF"


class UserRead(BaseModel):
    id: int
    organization_id: int
    name: str
    email: str
    role: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
