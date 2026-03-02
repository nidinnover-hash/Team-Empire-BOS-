from datetime import date, datetime

from pydantic import BaseModel, Field


class DepartmentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    code: str = Field(..., min_length=1, max_length=40)
    parent_department_id: int | None = Field(None, ge=1)


class DepartmentUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    code: str | None = Field(None, min_length=1, max_length=40)
    parent_department_id: int | None = Field(None, ge=1)
    is_active: bool | None = None


class DepartmentRead(BaseModel):
    id: int
    organization_id: int
    parent_department_id: int | None
    name: str
    code: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EmployeeOnboardRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    email: str = Field(..., min_length=3, max_length=320)
    role: str | None = Field(None, max_length=100)
    department_id: int | None = Field(None, ge=1)
    github_username: str | None = Field(None, max_length=100)
    clickup_user_id: str | None = Field(None, max_length=100)
    hired_at: datetime | None = None
    checklist: list[str] = Field(default_factory=list)
    notes: str | None = Field(None, max_length=2000)


class EmployeeOffboardRequest(BaseModel):
    effective_date: date | None = None
    checklist: list[str] = Field(default_factory=list)
    notes: str | None = Field(None, max_length=2000)


class EmployeeLifecycleEventRead(BaseModel):
    id: int
    organization_id: int
    employee_id: int
    event_type: str
    effective_date: date
    checklist_json: str
    notes: str | None
    actor_user_id: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


class WorkPatternUpsert(BaseModel):
    employee_id: int = Field(..., ge=1)
    work_date: date
    hours_logged: float = Field(0.0, ge=0)
    active_minutes: int = Field(0, ge=0)
    focus_minutes: int = Field(0, ge=0)
    meetings_minutes: int = Field(0, ge=0)
    tasks_completed: int = Field(0, ge=0)
    source: str = Field(default="manual", max_length=50)


class WorkPatternBulkUpsert(BaseModel):
    items: list[WorkPatternUpsert] = Field(default_factory=list, min_length=1, max_length=500)


class EmployeeWorkPatternRead(BaseModel):
    id: int
    organization_id: int
    employee_id: int
    work_date: date
    hours_logged: float
    active_minutes: int
    focus_minutes: int
    meetings_minutes: int
    tasks_completed: int
    source: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WorkPatternAnalyticsItem(BaseModel):
    employee_id: int
    employee_name: str
    department_id: int | None
    avg_hours_logged: float
    avg_focus_ratio: float
    total_tasks_completed: int
    activity_score: float


class WorkPatternAnalyticsRead(BaseModel):
    organization_id: int
    from_date: date
    to_date: date
    employees: list[WorkPatternAnalyticsItem]
