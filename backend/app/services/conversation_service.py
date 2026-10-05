from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Conversation, User
from app.models.user import utc_now


def create_conversation(db: Session, user: User, title: str) -> Conversation:
    conversation = Conversation(id=str(uuid4()), user_id=user.id, title=title.strip())
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


def list_conversations(db: Session, user: User) -> list[Conversation]:
    return list(
        db.scalars(
            select(Conversation)
            .where(Conversation.user_id == user.id)
            .order_by(Conversation.updated_at.desc(), Conversation.id)
        ).all()
    )


def get_owned_conversation(db: Session, user: User, thread_id: str) -> Conversation:
    conversation = db.get(Conversation, thread_id)
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")
    if conversation.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not own this conversation.")
    return conversation


def touch_conversation(
    db: Session,
    conversation: Conversation,
    *,
    initial_message: str | None = None,
) -> None:
    now = utc_now()
    conversation.updated_at = now
    if initial_message and conversation.title == "New conversation":
        conversation.title = initial_message.strip()[:42] or "New conversation"
    db.commit()


def delete_conversation(db: Session, conversation: Conversation) -> None:
    db.delete(conversation)
    db.commit()
