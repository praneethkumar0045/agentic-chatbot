from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.chat import ChatMessage


class ConversationCreate(BaseModel):
    title: str = Field(default="New conversation", min_length=1, max_length=120)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        title = value.strip()
        if not title:
            raise ValueError("Title cannot be blank.")
        return title


class ConversationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    created_at: datetime
    updated_at: datetime


class PendingApproval(BaseModel):
    type: str
    tool: str
    query: str


class ConversationRead(ConversationSummary):
    messages: list[ChatMessage] = Field(default_factory=list)
    pending_approval: PendingApproval | None = None
