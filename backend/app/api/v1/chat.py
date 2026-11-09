import uuid

from fastapi import APIRouter, Response, status

from app.api.deps import DbSession
from app.schemas.chat import (
    AnswerResponse,
    ConversationCreate,
    ConversationDetail,
    MessageCreate,
    MessageExchange,
    MessageRead,
    NewConversationMessage,
    QueryRequest,
    SearchRequest,
    SearchResponse,
)
from app.schemas.conversation import ConversationRead
from app.services import chat as service

router = APIRouter(tags=["chat"])

_ERRORS = {
    404: {"description": "Workspace, conversation or document not found"},
    422: {"description": "Invalid request, or nothing in scope has been processed yet"},
    502: {"description": "The generation provider failed"},
    503: {"description": "No LLM provider configured, or a model is not downloaded"},
}


@router.post("/search", response_model=SearchResponse, responses=_ERRORS)
def search(payload: SearchRequest, db: DbSession) -> SearchResponse:
    """Hybrid retrieval only (dense + BM25 + RRF + rerank). Works without an LLM."""
    return service.search(
        db, payload.workspace_id, payload.query, payload.document_ids, payload.languages, payload.top_k, payload.rerank
    )


@router.post("/chat/query", response_model=AnswerResponse, responses=_ERRORS)
def query(payload: QueryRequest, db: DbSession) -> AnswerResponse:
    """Answer one question from the workspace's documents, with citations. Not persisted."""
    return service.query(
        db, payload.workspace_id, payload.question, payload.document_ids, payload.languages, payload.response_language
    )


@router.post("/chat/conversations", response_model=ConversationRead, status_code=status.HTTP_201_CREATED)
def create_conversation(payload: ConversationCreate, db: DbSession) -> ConversationRead:
    conversation = service.create_conversation(db, payload.workspace_id, payload.title)
    return ConversationRead.model_validate(conversation)


@router.get("/chat/conversations/{conversation_id}", response_model=ConversationDetail)
def get_conversation(conversation_id: uuid.UUID, db: DbSession) -> ConversationDetail:
    return service.conversation_detail(db, conversation_id)


@router.delete("/chat/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(conversation_id: uuid.UUID, db: DbSession) -> Response:
    service.delete_conversation(db, conversation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/chat/messages", response_model=MessageExchange, status_code=status.HTTP_201_CREATED, responses=_ERRORS)
def start_conversation(payload: NewConversationMessage, db: DbSession) -> MessageExchange:
    """Ask the first question of a new conversation. The conversation is stored only if answering succeeds."""
    user_message, assistant_message, answer = service.send_message(
        db, None, payload.content, payload.document_ids, payload.languages, payload.response_language,
        workspace_id=payload.workspace_id,
    )
    return MessageExchange(
        conversation_id=user_message.conversation_id,
        user_message=MessageRead.model_validate(user_message),
        assistant_message=MessageRead.model_validate(assistant_message),
        answer=answer,
    )


@router.post(
    "/chat/conversations/{conversation_id}/messages",
    response_model=MessageExchange,
    status_code=status.HTTP_201_CREATED,
    responses=_ERRORS,
)
def send_message(conversation_id: uuid.UUID, payload: MessageCreate, db: DbSession) -> MessageExchange:
    """Ask a question in a conversation. Both messages are stored only if answering succeeds."""
    user_message, assistant_message, answer = service.send_message(
        db, conversation_id, payload.content, payload.document_ids, payload.languages, payload.response_language
    )
    return MessageExchange(
        conversation_id=conversation_id,
        user_message=MessageRead.model_validate(user_message),
        assistant_message=MessageRead.model_validate(assistant_message),
        answer=answer,
    )
