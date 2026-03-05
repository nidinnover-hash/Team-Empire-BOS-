from __future__ import annotations

from pydantic import BaseModel, Field


class OrgContext(BaseModel):
    id: int
    slug: str
    name: str
    country_code: str | None = None
    branch_label: str | None = None
    parent_organization_id: int | None = None
    policy: dict[str, object] = Field(default_factory=dict)


class EmployeeContext(BaseModel):
    employee_id: int
    name: str
    job_title: str | None = None
    department_id: int | None = None
    employment_status: str | None = None
    profile: dict[str, object] = Field(default_factory=dict)
    recent_work_pattern: dict[str, object] = Field(default_factory=dict)


class BrainContext(BaseModel):
    organization_id: int
    actor_user_id: int | None = None
    actor_role: str | None = None
    request_purpose: str = "professional"
    capabilities: list[str] = Field(default_factory=list)
    org: OrgContext
    employee: EmployeeContext | None = None
