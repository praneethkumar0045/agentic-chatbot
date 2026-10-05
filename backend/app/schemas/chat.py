from typing import List, Optional, Any
from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: str
    content: str
    metadata: Optional[dict[str, Any]] = None


class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    thread_id: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


class ChatResponse(BaseModel):
    messages: List[ChatMessage]
