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
    to: str = Field(min_length=1, max_length=500)
    subject: str = Field(min_length=1, max_length=500)
    instruction: str = Field(min_length=1, max_length=2000)


class GmailAuthUrlRead(BaseModel):
    auth_url: str
    state: str


class GmailHealthRead(BaseModel):
    status: str
    code: str | None = None
    email_address: str | None = None
    messages_total: int | None = None
    threads_total: int | None = None


class EmailSummaryResponse(BaseModel):
    email_id: int
    summary: str


class EmailDraftResponse(BaseModel):
    email_id: int
    draft: str
    status: str
    message: str


class EmailSendResponse(BaseModel):
    email_id: int
    status: str
    message: str


class EmailStrategyResponse(BaseModel):
    email_id: int
    strategy: str


class EmailComposeResponse(BaseModel):
    to: str
    subject: str
    draft: str
    status: str
    message: str


class ManagerReportTemplateRead(BaseModel):
    subject_prefix: str
    required_fields: list[str]
    markdown_template: str


class EmailControlItem(BaseModel):
    email_id: int
    classification: str
    confidence: float
    task_id: int | None = None
    approval_id: int | None = None
    notes: list[str] = Field(default_factory=list)


class EmailControlRunResponse(BaseModel):
    scanned: int
    processed: int
    tasks_created: int
    approvals_created: int
    drafts_created: int
    escalations_flagged: int
    items: list[EmailControlItem]


class PendingActionsDigestRead(BaseModel):
    org_id: int
    generated_at: str
    total_open_tasks: int
    total_pending_approvals: int
    lines: list[str]


class PendingActionsDigestDraftRead(BaseModel):
    ok: bool
    approval_id: int
    to: str
    subject: str
    preview: str
