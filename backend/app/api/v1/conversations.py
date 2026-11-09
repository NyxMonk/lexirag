import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.schemas.conversation import ConversationRead
from app.services import conversations as service

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("", response_model=list[ConversationRead])
def list_conversations(
    db: DbSession,
    workspace_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ConversationRead]:
    return service.list_conversations(db, workspace_id=workspace_id, limit=limit, offset=offset)
