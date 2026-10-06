from typing import Annotated
import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.v1.auth import get_current_user, router as auth_router
from app.api.v1.chat_utils import content_to_text, message_to_schema
from app.api.v1.conversations import router as conversations_router
from app.db.session import get_db
from app.models import User
from app.schemas.chat import ChatMessage, ChatRequest, ChatResponse
from app.services import chat_service
from app.services import conversation_service


router = APIRouter()
router.include_router(auth_router, prefix="/auth", tags=["auth"])
router.include_router(conversations_router)
DatabaseSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


@router.get("/")
def root():
    return {"status": "ok"}


@router.get("/health")
def health():
    return {"status": "ok"}


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, request: Request, db: DatabaseSession, user: CurrentUser):
    conversation = conversation_service.get_owned_conversation(db, user, req.thread_id)
    graph = request.app.state.chatbot
    pending = chat_service.pending_approval(graph, req.thread_id)
    if (req.approval_decision is None and pending is not None) or (
        req.approval_decision is not None and pending is None
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="There is no matching pending tool approval for this conversation.",
        )
    if req.approval_decision is None:
        existing_messages = list(conversation.messages)
        history = [ChatMessage.model_validate(message) for message in existing_messages]
        conversation_service.touch_conversation(
            db,
            conversation,
            initial_message=req.messages[0].content,
        )
        conversation_service.append_messages(
            db,
            conversation,
            [message.model_dump(include={"role", "content"}) for message in req.messages],
        )
    else:
        history = []
    result_msgs = chat_service.chat(
        req.messages,
        thread_id=req.thread_id,
        chatbot=graph,
        fallback_history=history,
        approval_decision=req.approval_decision,
    )
    response_messages = [message_to_schema(message) for message in result_msgs]
    if chat_service.pending_approval(graph, req.thread_id) is None:
        final_assistant = next(
            (
                message
                for message in reversed(response_messages)
                if message.role in {"assistant", "ai"} and message.content
            ),
            None,
        )
        if final_assistant is not None:
            conversation_service.append_messages(
                db,
                conversation,
                [final_assistant.model_dump(include={"role", "content"})],
            )
    return ChatResponse(messages=response_messages)


@router.post("/chat/stream")
def chat_stream(req: ChatRequest, request: Request, db: DatabaseSession, user: CurrentUser):
    conversation = conversation_service.get_owned_conversation(db, user, req.thread_id)
    graph = request.app.state.chatbot
    pending = chat_service.pending_approval(graph, req.thread_id)
    if (req.approval_decision is None and pending is not None) or (
        req.approval_decision is not None and pending is None
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="There is no matching pending tool approval for this conversation.",
        )

    history: list[ChatMessage] = []
    if req.approval_decision is None:
        history = [ChatMessage.model_validate(message) for message in conversation.messages]
        conversation_service.touch_conversation(
            db,
            conversation,
            initial_message=req.messages[0].content,
        )
        conversation_service.append_messages(
            db,
            conversation,
            [message.model_dump(include={"role", "content"}) for message in req.messages],
        )

    def gen():
        assistant_response = ""
        for chunk in chat_service.stream_chat(
            req.messages,
            thread_id=req.thread_id,
            chatbot=graph,
            fallback_history=history,
            approval_decision=req.approval_decision,
        ):
            if isinstance(chunk, dict) and chunk.get("type") == "approval_required":
                yield f"event: approval_required\ndata: {json.dumps({**chunk, 'thread_id': req.thread_id})}\n\n"
                continue
            content_str = content_to_text(getattr(chunk, "content", ""))
            chunk_type = getattr(chunk, "type", "")
            tool_calls = getattr(chunk, "tool_call_chunks", None) or getattr(
                chunk, "tool_calls", None
            )
            if tool_calls:
                yield f"data: {json.dumps({'content': 'Searching the web...', 'type': 'status'})}\n\n"
                continue
            is_tool_message = chunk_type.lower() in {"tool", "toolmessagechunk"} or bool(
                getattr(chunk, "tool_call_id", None)
            )
            if is_tool_message:
                continue
            assistant_response += content_str
            yield f"data: {json.dumps({'content': content_str, 'type': 'message'})}\n\n"
        if assistant_response and chat_service.pending_approval(graph, req.thread_id) is None:
            conversation_service.append_messages(
                db,
                conversation,
                [{"role": "assistant", "content": assistant_response}],
            )

    return StreamingResponse(gen(), media_type="text/event-stream")
