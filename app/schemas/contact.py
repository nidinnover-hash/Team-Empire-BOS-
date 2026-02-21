from datetime import datetime
from pydantic import BaseModel


class ContactCreate(BaseModel):
    name: str
    email: str | None = None
    phone: str | None = None
    company: str | None = None
    role: str | None = None
    relationship: str = "personal"  # personal | business | family | mentor | other
    notes: str | None = None


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
