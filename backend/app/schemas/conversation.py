import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    title: str
    message_count: int = 0
    created_at: datetime
    updated_at: datetime
