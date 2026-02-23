from typing import Any

from pydantic import BaseModel, Field


class TeamDashboardSummary(BaseModel):
    total_members: int
    members_with_plan: int
    members_without_plan: list[str]
    total_tasks_today: int
    tasks_done: int
    tasks_pending: int
    pending_approvals: int
    unread_emails: int


class TeamMemberToday(BaseModel):
    plan_status: str
    total_tasks: int
    done: int
    pending: int
    tasks: list[dict[str, Any]]


class TeamMemberDashboard(BaseModel):
    id: int
    name: str
    role: str | None = None
    team: str | None = None
    ai_level: str
    current_project: str | None = None
    today: TeamMemberToday


class TeamDashboardResponse(BaseModel):
    date: str
    summary: TeamDashboardSummary
    team: list[TeamMemberDashboard]


class DailyBriefingResponse(BaseModel):
    date: str
    generated_at: str
    briefing: str
    raw_data: TeamDashboardSummary


class ExecutiveCalendarEvent(BaseModel):
    content: str
    location: str | None = None


class ExecutiveCalendar(BaseModel):
    event_count: int
    events: list[ExecutiveCalendarEvent]


class ExecutiveApprovalItem(BaseModel):
    id: int
    approval_type: str
    status: str
    requested_by: int | None = None
    approved_by: int | None = None
    created_at: str | None = None
    approved_at: str | None = None


class ExecutiveApprovals(BaseModel):
    pending_count: int
    recent: list[ExecutiveApprovalItem]


class ExecutiveUnreadEmail(BaseModel):
    id: int
    from_address: str | None = Field(default=None, alias="from")
    subject: str | None = None
    received_at: str | None = None

    model_config = {"populate_by_name": True}


class ExecutiveInbox(BaseModel):
    unread_count: int
    recent_unread: list[ExecutiveUnreadEmail]


class ExecutiveBriefingResponse(BaseModel):
    date: str
    generated_at: str
    summary: TeamDashboardSummary
    team_summary: TeamDashboardSummary
    calendar: ExecutiveCalendar
    approvals: ExecutiveApprovals
    inbox: ExecutiveInbox
    today_priorities: list[str]


class DraftPlansResponse(BaseModel):
    drafted: int
    message: str
    plan_ids: list[int]


class TeamPlanRead(BaseModel):
    plan_id: int
    member_name: str
    member_role: str | None = None
    member_team: str | None = None
    date: str
    status: str
    tasks: list[dict[str, Any]]
    ai_reasoning: str
    approved_at: str | None = None


class ApprovePlanResponse(BaseModel):
    plan_id: int
    status: str
    approved_at: str


class CompleteTaskResponse(BaseModel):
    plan_id: int
    task_index: int
    marked_done: bool
    progress: str
