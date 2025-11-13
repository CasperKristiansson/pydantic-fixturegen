"""Notification events emitted during the order lifecycle."""

from datetime import datetime
from enum import Enum
from typing import Annotated
from uuid import UUID

from pydantic import EmailStr, Field

from .shared import LocalizedText, MarketplaceBaseModel


class NotificationChannel(str, Enum):
    email = "email"
    sms = "sms"
    push = "push"


class NotificationTemplate(MarketplaceBaseModel):
    key: Annotated[str, Field(pattern=r"^[a-z0-9_\.]+$")]
    subject: LocalizedText
    body: list[LocalizedText]


class NotificationEvent(MarketplaceBaseModel):
    event_id: UUID
    channel: NotificationChannel
    recipient: EmailStr
    template: NotificationTemplate
    sent_at: datetime
    metadata: dict[str, str] = Field(default_factory=dict)
