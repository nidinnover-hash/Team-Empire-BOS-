from datetime import datetime

from pydantic import BaseModel


class ExecutionRead(BaseModel):
    id: int
    organization_id: int
    approval_id: int
    triggered_by: int
    status: str
    output_json: dict
    error_text: str | None
    started_at: datetime
    finished_at: datetime | None

    model_config = {"from_attributes": True}
