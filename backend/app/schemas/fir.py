import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

Classification = Literal["cognizable", "non-cognizable", "bailable", "non-bailable", "depends"]


class FirAnalyzeRequest(BaseModel):
    """Analyse an FIR given either as a processed document or as pasted text."""

    document_id: uuid.UUID | None = Field(default=None, description="A processed FIR document.")
    workspace_id: uuid.UUID | None = Field(
        default=None, description="If given, the document must belong to this workspace."
    )
    text: str | None = Field(default=None, min_length=1, max_length=50_000, description="FIR text, if no document.")
    offence_date: date | None = Field(
        default=None, description="Date of the offence; overrides the date found in the FIR."
    )

    @model_validator(mode="after")
    def _one_source(self) -> "FirAnalyzeRequest":
        if (self.document_id is None) == (self.text is None):
            raise ValueError("Provide exactly one of document_id or text.")
        return self


class FirSource(BaseModel):
    kind: Literal["document", "text"]
    document_id: uuid.UUID | None = None
    document_name: str | None = None
    characters: int


class DateCandidateOut(BaseModel):
    date: date
    text: str
    kind: Literal["occurrence", "report", "other"]


class Correspondence(BaseModel):
    code: str
    section: str
    title: str | None


class Charge(BaseModel):
    section: str = Field(description="Section as normalised from the FIR, e.g. '498A' or '103(1)'.")
    code: str | None = Field(description="IPC, BNS, another Act's name, or null if unknown.")
    code_source: Literal["explicit", "offence_date", "unknown", "other_act"] = Field(
        description="Whether the FIR named the code, or it was inferred from the offence date."
    )
    matched_text: str = Field(description="The section list as it appears in the FIR (digits normalised).")
    in_reference: bool = Field(description="True if the section is in the reference table.")
    reference_section: str | None = Field(
        default=None, description="Reference entry used; differs from 'section' for a closest match."
    )
    title: str | None = None
    kind: Literal["offence", "liability"] | None = None
    punishment: str | None = None
    cognizable: Classification | None = None
    bailable: Classification | None = None
    court: str | None = None
    note: str | None = None
    corresponds_to: list[Correspondence] = Field(
        default_factory=list, description="Approximate IPC<->BNS counterpart (unofficial)."
    )


class ReferenceInfo(BaseModel):
    validated: bool
    sources: list[str]
    caveats: list[str]


class FirAnalysis(BaseModel):
    source: FirSource
    offence_date: date | None
    offence_date_source: Literal["provided", "occurrence", "earliest", "none"]
    date_candidates: list[DateCandidateOut]
    applicable_code: Literal["IPC", "BNS"] | None = Field(description="Code in force on the offence date.")
    bns_commencement: date
    charges: list[Charge]
    reference: ReferenceInfo
    warnings: list[str]
    disclaimer: str = (
        "Automated reading of the FIR against a reference table. Not legal advice; "
        "confirm the sections and their classification with a lawyer."
    )
