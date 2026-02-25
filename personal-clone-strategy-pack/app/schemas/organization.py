from datetime import datetime

from pydantic import BaseModel, Field


class OrganizationCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    slug: str = Field(..., min_length=1, max_length=100)


class OrganizationUpdate(BaseModel):
    name: str | None = Field(None, max_length=200)
    slug: str | None = Field(None, max_length=100)


class OrganizationRead(BaseModel):
    id: int
    name: str
    slug: str
    created_at: datetime

    model_config = {"from_attributes": True}
