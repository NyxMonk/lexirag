import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models import Conversation, Document, Workspace
from app.schemas.workspace import WorkspaceCreate, WorkspaceRead
from app.services.storage import LocalStorage

logger = logging.getLogger("lexirag.workspaces")


def _with_counts():
    doc_count = (
        select(func.count(Document.id))
        .where(Document.workspace_id == Workspace.id)
        .correlate(Workspace)
        .scalar_subquery()
    )
    conv_count = (
        select(func.count(Conversation.id))
        .where(Conversation.workspace_id == Workspace.id)
        .correlate(Workspace)
        .scalar_subquery()
    )
    return select(Workspace, doc_count.label("dc"), conv_count.label("cc"))


def _to_read(row) -> WorkspaceRead:
    workspace, doc_count, conv_count = row
    return WorkspaceRead.model_validate(workspace).model_copy(
        update={"document_count": doc_count, "conversation_count": conv_count}
    )


def list_workspaces(db: Session, *, limit: int, offset: int) -> list[WorkspaceRead]:
    stmt = (
        _with_counts()
        .order_by(Workspace.updated_at.desc(), Workspace.id)
        .limit(limit)
        .offset(offset)
    )
    return [_to_read(row) for row in db.execute(stmt).all()]


def get_workspace(db: Session, workspace_id: uuid.UUID) -> WorkspaceRead:
    row = db.execute(_with_counts().where(Workspace.id == workspace_id)).one_or_none()
    if row is None:
        raise NotFoundError("Workspace not found.")
    return _to_read(row)


def create_workspace(db: Session, data: WorkspaceCreate) -> WorkspaceRead:
    workspace = Workspace(name=data.name, description=data.description)
    db.add(workspace)
    db.commit()
    db.refresh(workspace)
    logger.info("Created workspace %s", workspace.id)
    return WorkspaceRead.model_validate(workspace)


def delete_workspace(db: Session, storage: LocalStorage, workspace_id: uuid.UUID) -> None:
    workspace = db.get(Workspace, workspace_id)
    if workspace is None:
        raise NotFoundError("Workspace not found.")
    paths = db.scalars(select(Document.file_path).where(Document.workspace_id == workspace_id)).all()
    db.delete(workspace)
    db.commit()
    # Files are removed only after the database commit succeeds.
    for path in paths:
        storage.delete(path)
    storage.delete_workspace_dir(workspace_id)
    logger.info("Deleted workspace %s and %d document(s)", workspace_id, len(paths))
