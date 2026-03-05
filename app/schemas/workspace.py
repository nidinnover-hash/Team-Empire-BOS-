"""Schemas for Workspace CRUD and membership."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

WorkspaceType = Literal["general", "department", "project", "client"]


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    slug: str = Field(min_length=1, max_length=120, pattern=r"^[a-z0-9\-]+$")
    workspace_type: WorkspaceType = "general"
    description: str | None = None


class WorkspaceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    workspace_type: WorkspaceType | None = None
    description: str | None = None
    is_active: bool | None = None


class WorkspaceRead(BaseModel):
    id: int
    organization_id: int
    name: str
    slug: str
    workspace_type: str
    description: str | None = None
    is_default: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WorkspaceMemberAdd(BaseModel):
    user_id: int
    role_override: str | None = Field(default=None, max_length=30)


class WorkspaceMemberRead(BaseModel):
    id: int
    workspace_id: int
    user_id: int
    role_override: str | None = None
    is_active: bool
    joined_at: datetime

    model_config = {"from_attributes": True}
