from datetime import datetime

from pydantic import BaseModel, Field


class UnifiedInboxItem(BaseModel):
    channel: str  # email | whatsapp
    item_id: int
    external_id: str | None = None
    direction: str | None = None
    from_address: str | None = None
    to_address: str | None = None
    subject: str | None = None
    preview: str | None = None
    status: str | None = None
    is_read: bool | None = None
    timestamp: datetime | None = None


class UnifiedConversation(BaseModel):
    record_id: int
    conversation_id: str
    channel: str
    participant: str | None = None
    owner_user_id: int | None = None
    priority: str
    status: str
    sla_due_at: datetime | None = None
    message_count: int
    unread_count: int
    last_message: UnifiedInboxItem


class ConversationAssignRequest(BaseModel):
    owner_user_id: int | None = None


class ConversationStateUpdateRequest(BaseModel):
    status: str | None = Field(default=None, pattern="^(new|in_review|waiting|done)$")
    priority: str | None = Field(default=None, pattern="^(low|medium|high|urgent)$")
    sla_due_at: datetime | None = None
