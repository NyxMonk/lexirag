"""FIR explainer: deterministic charge card from an FIR (no LLM involved)."""

import logging
import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import InvalidRequestError, NotFoundError
from app.models import Document, DocumentChunk, ProcessingStatus
from app.rag import fir
from app.schemas.fir import (
    Charge,
    Correspondence,
    DateCandidateOut,
    FirAnalysis,
    FirSource,
    ReferenceInfo,
)

logger = logging.getLogger("lexirag.fir")


def _document_text(db: Session, document_id: uuid.UUID, workspace_id: uuid.UUID | None) -> tuple[Document, str]:
    document = db.get(Document, document_id)
    # A document from another workspace is reported as not found (no cross-workspace probing).
    if document is None or (workspace_id is not None and document.workspace_id != workspace_id):
        raise NotFoundError("Document not found.")
    if document.processing_status != ProcessingStatus.COMPLETED.value:
        raise InvalidRequestError("This document has not finished processing yet.")
    contents = db.scalars(
        select(DocumentChunk.content)
        .where(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.chunk_index)
    ).all()
    text = "\n".join(contents)
    if not text.strip():
        raise InvalidRequestError("No text could be read from this document.")
    return document, text


def _charge(ref: fir.SectionRef) -> Charge:
    charge = Charge(
        section=ref.section,
        code=ref.code,
        code_source=ref.label_source,  # type: ignore[arg-type]
        matched_text=ref.matched_text,
        in_reference=False,
    )
    if ref.code not in ("IPC", "BNS"):
        return charge
    key, entry = fir.lookup_offence(ref.code, ref.section)
    if entry is None:
        return charge
    other_code = "BNS" if ref.code == "IPC" else "IPC"
    other_table = fir.load_offence_table()[other_code]
    return charge.model_copy(
        update={
            "in_reference": True,
            "reference_section": key,
            "title": entry["title"],
            "kind": entry["kind"],
            "punishment": entry["punishment"],
            "cognizable": entry["cognizable"],
            "bailable": entry["bailable"],
            "court": entry["court"],
            "note": entry.get("note"),
            "corresponds_to": [
                Correspondence(code=other_code, section=s, title=(other_table.get(s) or {}).get("title"))
                for s in entry["corresponds_to"]
            ],
        }
    )


def analyze(
    db: Session,
    *,
    document_id: uuid.UUID | None,
    workspace_id: uuid.UUID | None,
    text: str | None,
    offence_date: date | None,
) -> FirAnalysis:
    if document_id is not None:
        document, text = _document_text(db, document_id, workspace_id)
        source = FirSource(
            kind="document", document_id=document.id, document_name=document.original_filename, characters=len(text)
        )
    else:
        assert text is not None
        source = FirSource(kind="text", characters=len(text))

    result = fir.analyse_fir(text, offence_date)
    charges = [_charge(s) for s in result.sections]
    warnings = list(result.warnings)
    if not charges:
        warnings.append("No penal sections were found. Check that the FIR text is readable (scanned FIRs need OCR).")
    closest = [c.section for c in charges if c.in_reference and c.reference_section != c.section]
    if closest:
        warnings.append(
            "Matched to the nearest listed provision: " + ", ".join(closest) + ". Check the exact sub-section."
        )
    meta = fir.load_offence_table()["meta"]
    logger.info(
        "Analysed FIR (%s, %d chars): %d sections, code=%s, date source=%s",
        source.kind, source.characters, len(charges), result.applicable_code, result.offence_date_source,
    )
    return FirAnalysis(
        source=source,
        offence_date=result.offence_date,
        offence_date_source=result.offence_date_source,  # type: ignore[arg-type]
        date_candidates=[
            DateCandidateOut(date=c.value, text=c.text, kind=c.kind)  # type: ignore[arg-type]
            for c in result.date_candidates
        ],
        applicable_code=result.applicable_code,  # type: ignore[arg-type]
        bns_commencement=fir.BNS_COMMENCEMENT,
        charges=charges,
        reference=ReferenceInfo(validated=meta["validated"], sources=meta["sources"], caveats=meta["caveats"]),
        warnings=warnings,
    )
