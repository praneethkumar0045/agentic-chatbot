from typing import Any
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class ChatMessage(BaseModel):
    role: str
    content: str
    metadata: dict[str, Any] | None = None


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(default_factory=list)
    thread_id: str = Field(min_length=1, max_length=36)
    temperature: float | None = None
    max_tokens: int | None = None
    approval_decision: Literal["approve", "reject"] | None = None

    @model_validator(mode="after")
    def validate_turn(self):
        if self.approval_decision is None and not self.messages:
            raise ValueError("At least one message is required for a new chat turn.")
        if self.approval_decision is not None and self.messages:
            raise ValueError("Approval decisions must not include new messages.")
        return self


class ChatResponse(BaseModel):
    messages: list[ChatMessage]
