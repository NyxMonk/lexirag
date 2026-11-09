from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.database.session import get_db
from app.services.storage import LocalStorage


def get_storage(settings: Annotated[Settings, Depends(get_settings)]) -> LocalStorage:
    return LocalStorage(settings.storage_path)


DbSession = Annotated[Session, Depends(get_db)]
Storage = Annotated[LocalStorage, Depends(get_storage)]
AppSettings = Annotated[Settings, Depends(get_settings)]
