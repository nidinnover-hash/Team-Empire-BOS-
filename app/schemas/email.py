from datetime import datetime

from pydantic import BaseModel, Field


class EmailRead(BaseModel):
    id: int
    gmail_id: str
    thread_id: str | None
    from_address: str | None
    to_address: str | None
    subject: str | None
    received_at: datetime | None
    is_read: bool
    category: str | None
    ai_summary: str | None
    draft_reply: str | None
    gmail_draft_id: str | None
    approval_id: int | None
    reply_approved: bool
    reply_sent: bool

    model_config = {"from_attributes": True}


class DraftReplyRequest(BaseModel):
    instruction: str = Field(default="", max_length=2000)


class SyncResult(BaseModel):
    new_emails: int
    message: str


class ComposeRequest(BaseModel):
    to: str = Field(max_length=500)
    subject: str = Field(max_length=500)
    instruction: str = Field(max_length=2000)
