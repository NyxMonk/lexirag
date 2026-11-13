from fastapi import APIRouter

from app.api.deps import DbSession
from app.schemas.fir import FirAnalysis, FirAnalyzeRequest
from app.services import fir as service

router = APIRouter(prefix="/fir", tags=["fir"])


@router.post(
    "/analyze",
    response_model=FirAnalysis,
    responses={
        404: {"description": "Document not found (or not in the given workspace)"},
        422: {"description": "Invalid request, or the document has not finished processing"},
    },
)
def analyze(payload: FirAnalyzeRequest, db: DbSession) -> FirAnalysis:
    """Find the penal sections and offence date in an FIR and build a charge card.

    Deterministic (no LLM): sections are parsed from the text and looked up in a reference table.
    Works without an LLM provider or the embedding model.
    """
    return service.analyze(
        db,
        document_id=payload.document_id,
        workspace_id=payload.workspace_id,
        text=payload.text,
        offence_date=payload.offence_date,
    )
