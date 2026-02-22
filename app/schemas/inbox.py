from datetime import datetime

from pydantic import BaseModel


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
    conversation_id: str
    channel: str
    participant: str | None = None
    message_count: int
    unread_count: int
    last_message: UnifiedInboxItem
