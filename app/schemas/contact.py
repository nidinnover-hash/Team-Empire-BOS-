from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

ContactRelationship = Literal["personal", "business", "family", "mentor", "other"]


class ContactCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    email: EmailStr | None = None
    phone: str | None = Field(None, max_length=30)
    company: str | None = Field(None, max_length=200)
    role: str | None = Field(None, max_length=100)
    relationship: ContactRelationship = "personal"
    notes: str | None = Field(None, max_length=2000)


class ContactUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    email: EmailStr | None = None
    phone: str | None = Field(None, max_length=30)
    company: str | None = Field(None, max_length=200)
    role: str | None = Field(None, max_length=100)
    relationship: ContactRelationship | None = None
    notes: str | None = Field(None, max_length=2000)


class ContactRead(BaseModel):
    id: int
    name: str
    email: str | None
    phone: str | None
    company: str | None
    role: str | None
    relationship: str
    notes: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
