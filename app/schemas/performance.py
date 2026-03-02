from datetime import date
from typing import Any

from pydantic import BaseModel


class DailyPattern(BaseModel):
    work_date: date
    hours_logged: float
    active_minutes: int
    focus_minutes: int
    meetings_minutes: int
    tasks_completed: int


class PerformanceTrend(BaseModel):
    period_label: str
    avg_hours: float
    avg_focus_ratio: float
    avg_tasks: float


class EmployeePerformance(BaseModel):
    employee_id: int
    employee_name: str
    department_id: int | None = None
    days_tracked: int
    avg_hours: float
    avg_focus_ratio: float
    avg_tasks_per_day: float
    total_tasks: int
    total_meetings_minutes: int
    composite_score: float
    trends: list[PerformanceTrend] = []


class DepartmentPerformance(BaseModel):
    department_id: int
    department_name: str
    employee_count: int
    avg_hours: float
    avg_focus_ratio: float
    avg_tasks_per_day: float
    total_tasks: int
    top_performers: list[EmployeePerformance] = []


class OrgPerformance(BaseModel):
    organization_id: int
    total_employees: int
    total_departments: int
    avg_hours: float
    avg_focus_ratio: float
    avg_tasks_per_day: float
    departments: list[DepartmentPerformance] = []


class PerformanceAlert(BaseModel):
    employee_id: int
    employee_name: str
    department_id: int | None = None
    composite_score: float
    alert_reason: str


class OrgChartNode(BaseModel):
    team_member_id: int
    name: str
    role_title: str | None = None
    team: str | None = None
    reports_to_id: int | None = None
    direct_reports_count: int
    ai_level: int
    skills: list[str]


class OrgChartRead(BaseModel):
    organization_id: int
    roots: list[int]
    nodes: list[OrgChartNode]


class WorkloadAction(BaseModel):
    from_member_id: int
    from_member_name: str
    to_member_id: int
    to_member_name: str
    suggested_task_moves: int
    reason: str


class WorkloadBalanceRead(BaseModel):
    organization_id: int
    for_date: date
    average_task_load: float
    overloaded_count: int
    underloaded_count: int
    actions: list[WorkloadAction]
    by_member: list[dict[str, Any]]


class SkillCoverage(BaseModel):
    skill: str
    members_count: int
    members: list[str]


class SkillGap(BaseModel):
    team_member_id: int
    team_member_name: str
    missing_skills: list[str]


class SkillMatrixRead(BaseModel):
    organization_id: int
    required_skills: list[str]
    coverage: list[SkillCoverage]
    member_gaps: list[SkillGap]
    org_missing_skills: list[str]


class DepartmentOKRKeyResult(BaseModel):
    key_result: str
    target: str
    actual: str
    progress_percent: int


class DepartmentOKRProgressRead(BaseModel):
    organization_id: int
    department_id: int
    department_name: str
    from_date: date
    to_date: date
    overall_progress_percent: int
    signals: dict[str, float | int]
    key_results: list[DepartmentOKRKeyResult]
