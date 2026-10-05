from typing import Annotated
import json

from fastapi import APIRouter, Depends
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
def chat(req: ChatRequest, db: DatabaseSession, user: CurrentUser):
    conversation = conversation_service.get_owned_conversation(db, user, req.thread_id)
    conversation_service.touch_conversation(
        db,
        conversation,
        initial_message=req.messages[0].content if req.messages else None,
    )
    existing_messages = list(conversation.messages)
    history = [ChatMessage.model_validate(message) for message in existing_messages]
    conversation_service.append_messages(
        db,
        conversation,
        [message.model_dump(include={"role", "content"}) for message in req.messages],
    )
    result_msgs = chat_service.chat(
        [*history, *req.messages],
        thread_id=req.thread_id,
    )
    response_messages = [message_to_schema(message) for message in result_msgs]
    conversation_service.append_messages(
        db,
        conversation,
        [
            message.model_dump(include={"role", "content"})
            for message in response_messages[len(existing_messages) + len(req.messages):]
            if message.role in {"assistant", "ai"}
        ],
    )
    return ChatResponse(messages=response_messages)


@router.post("/chat/stream")
def chat_stream(req: ChatRequest, db: DatabaseSession, user: CurrentUser):
    conversation = conversation_service.get_owned_conversation(db, user, req.thread_id)
    conversation_service.touch_conversation(
        db,
        conversation,
        initial_message=req.messages[0].content if req.messages else None,
    )
    existing_messages = list(conversation.messages)
    history = [ChatMessage.model_validate(message) for message in existing_messages]
    conversation_service.append_messages(
        db,
        conversation,
        [message.model_dump(include={"role", "content"}) for message in req.messages],
    )
    history.extend(req.messages)

    def gen():
        assistant_response = ""
        for chunk in chat_service.stream_chat(history, thread_id=req.thread_id):
            content_str = content_to_text(getattr(chunk, "content", ""))
            ctype = getattr(chunk, "type", "")
            if ctype != "tool":
                assistant_response += content_str
            yield f"data: {json.dumps({'content': content_str, 'type': ctype or 'message'})}\n\n"
        if assistant_response:
            conversation_service.append_messages(
                db,
                conversation,
                [{"role": "assistant", "content": assistant_response}],
            )

    return StreamingResponse(gen(), media_type="text/event-stream")
