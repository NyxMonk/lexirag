import uuid
from typing import Annotated

from fastapi import APIRouter, Body, File, Form, Query, Request, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select

from app.api.deps import AppSettings, DbSession, Storage
from app.core.errors import NotFoundError, PayloadTooLargeError
from app.models import DocumentChunk, ProcessingStatus
from app.schemas.document import (
    ChunkPage,
    ChunkRead,
    DocumentRead,
    DocumentStatus,
    DocumentUpdate,
    ProcessRequest,
)
from app.schemas.chat import AnswerResponse, SummaryRequest
from app.services import chat as chat_service
from app.services import documents as service
from app.services import processing

router = APIRouter(prefix="/documents", tags=["documents"])

# Allowance for multipart boundaries and form fields on top of the file itself.
MULTIPART_OVERHEAD = 64 * 1024


@router.get("", response_model=list[DocumentRead])
def list_documents(
    db: DbSession,
    workspace_id: uuid.UUID | None = None,
    search: Annotated[str | None, Query(max_length=200)] = None,
    status_filter: Annotated[ProcessingStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[DocumentRead]:
    documents = service.list_documents(
        db,
        workspace_id=workspace_id,
        search=search.strip() if search else None,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    return [DocumentRead.from_model(d) for d in documents]


@router.post("/upload", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
def upload_document(
    request: Request,
    db: DbSession,
    storage: Storage,
    settings: AppSettings,
    workspace_id: Annotated[uuid.UUID, Form()],
    file: Annotated[UploadFile, File(description="PDF document")],
) -> DocumentRead:
    declared = request.headers.get("content-length")
    if declared and declared.isdigit():
        if int(declared) > settings.max_upload_size_bytes + MULTIPART_OVERHEAD:
            raise PayloadTooLargeError(
                f"File exceeds the {settings.max_upload_size_mb} MB upload limit."
            )
    document = service.create_document(
        db,
        storage,
        workspace_id=workspace_id,
        filename=file.filename,
        content_type=file.content_type,
        source=file.file,
        max_bytes=settings.max_upload_size_bytes,
    )
    if settings.auto_process_uploads:
        processing.enqueue(db, document.id)
        db.refresh(document)
    return DocumentRead.from_model(document)


@router.get("/{document_id}", response_model=DocumentRead)
def get_document(document_id: uuid.UUID, db: DbSession) -> DocumentRead:
    return DocumentRead.from_model(service.get_document(db, document_id))


@router.patch("/{document_id}", response_model=DocumentRead)
def update_document(document_id: uuid.UUID, payload: DocumentUpdate, db: DbSession) -> DocumentRead:
    """Override (or clear) the detected document language."""
    return DocumentRead.from_model(service.set_language_override(db, document_id, payload.language_override))


@router.get(
    "/{document_id}/file",
    response_class=FileResponse,
    responses={200: {"content": {"application/pdf": {}}}},
)
def get_document_file(document_id: uuid.UUID, db: DbSession, storage: Storage) -> FileResponse:
    document = service.get_document(db, document_id)
    path = storage.resolve(document.file_path)
    if not path.is_file():
        raise NotFoundError("The stored file for this document is missing.")
    return FileResponse(
        path,
        media_type=document.mime_type,
        filename=document.original_filename,
        content_disposition_type="inline",
    )


@router.post("/{document_id}/process", response_model=DocumentRead, status_code=status.HTTP_202_ACCEPTED)
def process_document(
    document_id: uuid.UUID,
    db: DbSession,
    payload: Annotated[ProcessRequest | None, Body()] = None,
) -> DocumentRead:
    """Queue extraction, chunking, embedding and indexing. 409 if already running or done (unless force)."""
    processing.enqueue(db, document_id, force=bool(payload and payload.force))
    return DocumentRead.from_model(service.get_document(db, document_id))


@router.post("/{document_id}/retry", response_model=DocumentRead, status_code=status.HTTP_202_ACCEPTED)
def retry_document(document_id: uuid.UUID, db: DbSession) -> DocumentRead:
    """Re-queue a document whose processing failed."""
    processing.enqueue(db, document_id, retry_only=True)
    return DocumentRead.from_model(service.get_document(db, document_id))


@router.get("/{document_id}/status", response_model=DocumentStatus)
def document_status(document_id: uuid.UUID, db: DbSession) -> DocumentStatus:
    document = service.get_document(db, document_id)
    read = DocumentRead.from_model(document)
    details = document.processing_details or {}
    return DocumentStatus(
        id=document.id,
        processing_status=read.processing_status,
        processing_error=read.processing_error,
        processing_progress=read.processing_progress,
        page_count=read.page_count,
        chunk_count=read.chunk_count,
        detected_language=read.detected_language,
        language_status=read.language_status,
        processing_started_at=read.processing_started_at,
        processing_completed_at=read.processing_completed_at,
        extraction=details.get("extraction") if isinstance(details, dict) else None,
    )


@router.get("/{document_id}/chunks", response_model=ChunkPage)
def list_chunks(
    document_id: uuid.UUID,
    db: DbSession,
    page: Annotated[int | None, Query(ge=1, description="Only chunks covering this PDF page")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ChunkPage:
    service.get_document(db, document_id)
    where = [DocumentChunk.document_id == document_id]
    if page is not None:
        where += [DocumentChunk.page_start <= page, DocumentChunk.page_end >= page]
    total = db.scalar(select(func.count(DocumentChunk.id)).where(*where)) or 0
    rows = db.scalars(
        select(DocumentChunk).where(*where).order_by(DocumentChunk.chunk_index).limit(limit).offset(offset)
    ).all()
    return ChunkPage(items=[ChunkRead.model_validate(r) for r in rows], total=total)


@router.get("/{document_id}/chunks/{chunk_id}", response_model=ChunkRead)
def get_chunk(document_id: uuid.UUID, chunk_id: uuid.UUID, db: DbSession) -> ChunkRead:
    chunk = db.get(DocumentChunk, chunk_id)
    if chunk is None or chunk.document_id != document_id:
        raise NotFoundError("Chunk not found.")
    return ChunkRead.model_validate(chunk)


@router.post(
    "/{document_id}/summary",
    response_model=AnswerResponse,
    responses={422: {"description": "Not processed yet"}, 503: {"description": "No LLM provider configured"}},
)
def summarize_document(document_id: uuid.UUID, payload: SummaryRequest, db: DbSession) -> AnswerResponse:
    """Summary with key points and page citations, in the requested language. Long documents are sampled."""
    return chat_service.summarize_document(db, document_id, payload.response_language)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(document_id: uuid.UUID, db: DbSession, storage: Storage) -> Response:
    service.delete_document(db, storage, document_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
