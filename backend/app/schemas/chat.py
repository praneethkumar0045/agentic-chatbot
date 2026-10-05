from typing import Any

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str
    content: str
    metadata: dict[str, Any] | None = None


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1)
    thread_id: str = Field(min_length=1, max_length=36)
    temperature: float | None = None
    max_tokens: int | None = None


class ChatResponse(BaseModel):
    messages: list[ChatMessage]
