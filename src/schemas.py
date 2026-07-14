from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class WorkflowType(str, Enum):
    ALM_GAC = "ALM/GAC"
    LANDMAN = "Landman"


class ProjectType(str, Enum):
    MOR = "MOR"
    DUE_DILIGENCE = "DUE_DILIGENCE"


class ClassificationStatus(str, Enum):
    INCLUDE_FULL = "INCLUDE_FULL"
    INCLUDE_LIMITED = "INCLUDE_LIMITED"
    REDLINE = "REDLINE"
    REVIEW = "REVIEW"
    DUPLICATE = "DUPLICATE"


class LeaseStatus(str, Enum):
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    RELEASED = "RELEASED"
    REVIEW = "REVIEW"


class ProjectMetadata(BaseModel):
    project_name: str = "Untitled Project"
    county: str = "Arapahoe"
    state: str = "Colorado"
    section: str | None = None
    township: str | None = None
    range: str | None = None
    tract_legal_description: str | None = None
    workflow_type: WorkflowType = WorkflowType.ALM_GAC
    project_type: ProjectType = ProjectType.MOR
    unit_name: str | None = None


class SourceDocument(BaseModel):
    source_document_id: str
    source_row_number: int
    source_file_name: str | None = None
    original_file_name: str | None = None
    document_type: str | None = None
    document_title: str | None = None
    instrument_number: str | None = None
    book: str | None = None
    page: str | None = None
    effective_date: date | None = None
    instrument_date: date | None = None
    recording_date: date | None = None
    grantor: str | None = None
    grantee: str | None = None
    acreage: str | None = None
    conveyance: str | None = None
    legal_description: str | None = None
    comments: str | None = None
    source_trace: dict[str, Any] = Field(default_factory=dict)
    raw: dict[str, Any] = Field(default_factory=dict)
    duplicate_of: str | None = None
    dedupe_confidence: float | None = None
    status: ClassificationStatus | None = None
    classification_confidence: float | None = None
    classification_reason: str | None = None
    redline_reason: str | None = None
    review_question: str | None = None
    lease_status: LeaseStatus | None = None
    matched_source_file: str | None = None
    source_match_confidence: float | None = None
    source_match_method: str | None = None
    extracted_text_path: str | None = None
    pdf_extraction_status: str | None = None
    pdf_extraction_confidence: float | None = None
    pdf_page_count: int | None = None
    pdf_text_preview: str | None = None
    possible_document_type_keywords: list[str] = Field(default_factory=list)
    possible_legal_description_snippets: list[str] = Field(default_factory=list)
    possible_lease_primary_term_snippets: list[str] = Field(default_factory=list)
    # LLM extraction tracking
    llm_extraction_model: str | None = None
    llm_conveyance_confidence: float | None = None
    llm_comments_confidence: float | None = None
    # Due Diligence: typed convenience copy of the controlling title opinion's
    # certification date this record was filtered against (also in source_trace).
    certification_date: date | None = None

    def search_text(self) -> str:
        values = [
            self.document_type,
            self.document_title,
            self.instrument_number,
            self.grantor,
            self.grantee,
            self.legal_description,
            self.comments,
        ]
        return " ".join(str(value) for value in values if value)


class QAException(BaseModel):
    severity: str
    code: str
    message: str
    source_document_id: str | None = None
    field: str | None = None


class ProcessingSummary(BaseModel):
    total_documents: int
    processed_documents: int
    included: int
    redlined: int
    review: int
    duplicates: int
    errors: int
    template_check_status: str
    output_files: dict[str, str] = Field(default_factory=dict)
