from datetime import date, datetime

from pydantic import BaseModel


class DailyRunRead(BaseModel):
    id: int
    organization_id: int
    run_date: date
    team_filter: str
    requested_by: int
    status: str
    drafted_plan_count: int
    drafted_email_count: int
    pending_approvals: int
    result_json: dict
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}
