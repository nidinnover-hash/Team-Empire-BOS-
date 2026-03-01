from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ApiKeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    scopes: str = Field(default="*", max_length=500)
    expires_in_days: int | None = Field(None, ge=1, le=365)


class ApiKeyCreateResponse(BaseModel):
    id: int
    name: str
    key: str  # Full key — shown only once
    key_prefix: str
    scopes: str
    expires_at: datetime | None
    created_at: datetime


class ApiKeyRead(BaseModel):
    id: int
    name: str
    key_prefix: str
    scopes: str
    is_active: bool
    expires_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ApiKeyListResponse(BaseModel):
    count: int
    items: list[ApiKeyRead]
