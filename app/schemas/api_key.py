from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class ApiKeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    scopes: str = Field(default="read,write", max_length=500)
    expires_in_days: int | None = Field(None, ge=1, le=365)

    @field_validator("scopes", mode="before")
    @classmethod
    def normalize_scopes(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("Scopes must be a comma-separated string")
        parts = [part.strip().lower() for part in value.split(",") if part.strip()]
        if not parts:
            raise ValueError("At least one scope is required")
        allowed = {"*", "read", "write"}
        for part in parts:
            if part not in allowed:
                raise ValueError(f"Unknown scope: {part}")
        # "*" is exclusive to avoid ambiguous combinations.
        if "*" in parts and len(parts) > 1:
            raise ValueError("'*' scope cannot be combined with other scopes")
        deduped = list(dict.fromkeys(parts))
        return ",".join(deduped)


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
