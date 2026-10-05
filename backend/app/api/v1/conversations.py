from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.v1.auth import get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas.conversation import ConversationCreate, ConversationRead, ConversationSummary
from app.services import conversation_service


router = APIRouter(prefix="/conversations", tags=["conversations"])
DatabaseSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


@router.post("", response_model=ConversationSummary, status_code=status.HTTP_201_CREATED)
def create_conversation(payload: ConversationCreate, db: DatabaseSession, user: CurrentUser):
    return conversation_service.create_conversation(db, user, payload.title)


@router.get("", response_model=list[ConversationSummary])
def list_conversations(db: DatabaseSession, user: CurrentUser):
    return conversation_service.list_conversations(db, user)


@router.get("/{thread_id}", response_model=ConversationRead)
def get_conversation(thread_id: str, db: DatabaseSession, user: CurrentUser):
    conversation = conversation_service.get_owned_conversation(db, user, thread_id)
    return ConversationRead(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        messages=conversation.messages,
    )


@router.delete("/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(thread_id: str, db: DatabaseSession, user: CurrentUser) -> Response:
    conversation = conversation_service.get_owned_conversation(db, user, thread_id)
    conversation_service.delete_conversation(db, conversation)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
