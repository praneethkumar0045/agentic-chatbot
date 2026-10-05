from fastapi import APIRouter
from fastapi.responses import StreamingResponse, JSONResponse
import json

from app.schemas.chat import ChatRequest, ChatResponse, ChatMessage
from app.services import chat_service
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage, SystemMessage
from app.api.v1.auth import router as auth_router


def _content_to_text(content):
    if isinstance(content, list):
        text_parts = []
        for part in content:
            if isinstance(part, str):
                text_parts.append(part)
            elif isinstance(part, dict) and isinstance(part.get("text"), str):
                text_parts.append(part["text"])
        return "".join(text_parts)
    if content is None:
        return ""
    return content if isinstance(content, str) else str(content)


def _msg_to_schema(m):
    if isinstance(m, HumanMessage):
        role = "user"
    elif isinstance(m, AIMessage):
        role = "assistant"
    elif isinstance(m, ToolMessage):
        role = "tool"
    elif isinstance(m, SystemMessage):
        role = "system"
    else:
        t = getattr(m, "type", None) or getattr(m, "role", None) or "assistant"
        role = "assistant" if t == "thought" else t
    content = _content_to_text(getattr(m, "content", ""))
    return ChatMessage(role=role, content=content)


router = APIRouter()
router.include_router(auth_router, prefix="/auth", tags=["auth"])


@router.get("/")
def root():
    return {"status": "ok"}


@router.get("/health")
def health():
    return {"status": "ok"}


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    result_msgs = chat_service.chat(req.messages, thread_id=req.thread_id or "default")
    return ChatResponse(messages=[_msg_to_schema(m) for m in result_msgs])


@router.post("/chat/stream")
def chat_stream(req: ChatRequest):
    def gen():
        for chunk in chat_service.stream_chat(req.messages, thread_id=req.thread_id or "default"):
            content_str = _content_to_text(getattr(chunk, "content", ""))
            ctype = getattr(chunk, "type", "")
            yield f"data: {json.dumps({'content': content_str, 'type': ctype or 'message'})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")
