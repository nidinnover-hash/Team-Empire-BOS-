import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field

ContextType = Literal["priority", "meeting", "blocker", "decision", "slack", "auto_briefing"]


# ── Profile Memory ────────────────────────────────────────────────────────────

class ProfileMemoryCreate(BaseModel):
    key: str = Field(..., max_length=100, description="Unique key e.g. 'business_rule', 'personal_goal'")
    value: str = Field(..., max_length=5000, description="The memory content")
    category: str | None = Field(None, max_length=50)
    expires_at: dt.datetime | None = Field(None, description="Auto-expire this memory entry after this time")


class ProfileMemoryRead(BaseModel):
    id: int
    organization_id: int
    key: str
    value: str
    category: str | None
    expires_at: dt.datetime | None = None
    updated_at: dt.datetime

    model_config = {"from_attributes": True}


# ── Team Member ───────────────────────────────────────────────────────────────

class TeamMemberCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    role_title: str | None = Field(None, max_length=100, description="e.g. Developer, Tech Head, Counsellor")
    team: str | None = Field(None, max_length=50, description="tech | sales | ops | admin")
    reports_to_id: int | None = Field(None, description="ID of the team member they report to")
    skills: str | None = Field(None, max_length=500, description="Comma-separated skills")
    ai_level: int = Field(1, ge=1, le=5, description="1=none, 2=basic, 3=intermediate, 4=advanced, 5=expert")
    current_project: str | None = Field(None, max_length=200)
    notes: str | None = Field(None, max_length=2000)
    user_id: int | None = Field(None, description="Link to auth user if they have login access")


class TeamMemberUpdate(BaseModel):
    role_title: str | None = Field(None, max_length=100)
    team: str | None = Field(None, max_length=50)
    reports_to_id: int | None = None
    skills: str | None = Field(None, max_length=500)
    ai_level: int | None = Field(None, ge=1, le=5)
    current_project: str | None = Field(None, max_length=200)
    notes: str | None = Field(None, max_length=2000)
    is_active: bool | None = None


class TeamMemberRead(BaseModel):
    id: int
    organization_id: int
    name: str
    role_title: str | None
    team: str | None
    reports_to_id: int | None
    skills: str | None
    ai_level: int
    current_project: str | None
    notes: str | None
    is_active: bool
    user_id: int | None

    model_config = {"from_attributes": True}


# ── Daily Context ─────────────────────────────────────────────────────────────

class DailyContextCreate(BaseModel):
    date: dt.date = Field(..., description="The date this context belongs to")
    context_type: ContextType = Field(..., description="priority | meeting | blocker | decision | slack")
    content: str = Field(..., min_length=1, max_length=5000, description="The actual context content")
    related_to: str | None = Field(None, max_length=100, description="Name or entity this relates to")


class DailyContextRead(BaseModel):
    id: int
    organization_id: int
    date: dt.date
    context_type: str
    content: str
    related_to: str | None
    created_at: dt.datetime

    model_config = {"from_attributes": True}
