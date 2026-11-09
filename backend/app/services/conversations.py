import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Conversation, Message
from app.schemas.conversation import ConversationRead


def list_conversations(
    db: Session, *, workspace_id: uuid.UUID | None, limit: int, offset: int
) -> list[ConversationRead]:
    msg_count = (
        select(func.count(Message.id))
        .where(Message.conversation_id == Conversation.id)
        .correlate(Conversation)
        .scalar_subquery()
    )
    stmt = select(Conversation, msg_count)
    if workspace_id is not None:
        stmt = stmt.where(Conversation.workspace_id == workspace_id)
    stmt = stmt.order_by(Conversation.updated_at.desc(), Conversation.id).limit(limit).offset(offset)
    return [
        ConversationRead.model_validate(conv).model_copy(update={"message_count": count})
        for conv, count in db.execute(stmt).all()
    ]
