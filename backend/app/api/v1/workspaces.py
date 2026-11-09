import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import DbSession, Storage
from app.schemas.workspace import WorkspaceCreate, WorkspaceRead
from app.services import workspaces as service

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


@router.get("", response_model=list[WorkspaceRead])
def list_workspaces(
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[WorkspaceRead]:
    return service.list_workspaces(db, limit=limit, offset=offset)


@router.post("", response_model=WorkspaceRead, status_code=status.HTTP_201_CREATED)
def create_workspace(payload: WorkspaceCreate, db: DbSession) -> WorkspaceRead:
    return service.create_workspace(db, payload)


@router.get("/{workspace_id}", response_model=WorkspaceRead)
def get_workspace(workspace_id: uuid.UUID, db: DbSession) -> WorkspaceRead:
    return service.get_workspace(db, workspace_id)


@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workspace(workspace_id: uuid.UUID, db: DbSession, storage: Storage) -> Response:
    service.delete_workspace(db, storage, workspace_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
