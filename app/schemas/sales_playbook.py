"""Sales playbook and step schemas for CRM."""

from pydantic import BaseModel, Field


class PlaybookStepCreate(BaseModel):
    step_order: int = Field(0, ge=0)
    title: str = Field(..., min_length=1, max_length=255)
    content: str | None = None
    is_required: bool = False


class PlaybookStepUpdate(BaseModel):
    step_order: int | None = Field(None, ge=0)
    title: str | None = Field(None, min_length=1, max_length=255)
    content: str | None = None
    is_required: bool | None = None


class PlaybookCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    deal_stage: str | None = Field(None, max_length=50)
    description: str | None = None
    is_active: bool = True
    steps: list[PlaybookStepCreate] = Field(default_factory=list)


class PlaybookUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    deal_stage: str | None = Field(None, max_length=50)
    description: str | None = None
    is_active: bool | None = None
