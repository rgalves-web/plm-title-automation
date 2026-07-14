from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from src.excel_writer import TemplateCheckResult
from src.lease_engine import is_oil_and_gas_lease
from src.pdf_reader import EXTRACTION_ERROR, LOW_CONFIDENCE_TEXT, OCR_REQUIRED
from src.schemas import ClassificationStatus, LeaseStatus, ProjectMetadata, QAException, SourceDocument
from src.utils import enum_value, model_to_dict


_OGL_TYPE_KEYWORDS = ("oil and gas lease", "oil & gas lease", "o&g lease", "oil gas lease")


def _is_ogl_by_type(r: SourceDocument) -> bool:
    doc_type = (r.document_type or "").lower()
    return any(kw in doc_type for kw in _OGL_TYPE_KEYWORDS)


class QAHardStopError(RuntimeError):
    def __init__(self, exceptions: list[QAException]) -> None:
        self.exceptions = exceptions
        codes = ", ".join(exception.code for exception in exceptions)
        super().__init__(
            "Final runsheet export blocked by QA hard-stop validation(s): "
            f"{codes}"
        )


def run_qa(
    records: list[SourceDocument],
    expected_document_count: int | None = None,
    template_check: TemplateCheckResult | dict[str, Any] | None = None,
    source_verification_required: bool = False,
    metadata: ProjectMetadata | dict[str, Any] | None = None,
    accepted_missing_sources: list[str] | None = None,
) -> list[QAException]:
    exceptions: list[QAException] = []
    _accepted = set(accepted_missing_sources or [])

    if expected_document_count is not None and len(records) != expected_document_count:
        exceptions.append(
            QAException(
                severity="ERROR",
                code="DOCUMENT_COUNT_MISMATCH",
                message=(
                    f"Document Register has {len(records)} rows, expected "
                    f"{expected_document_count} rows from the Document List."
                ),
            )
        )

    for record in records:
        _qa_record(record, exceptions)
        _qa_source_verification(record, exceptions, source_verification_required, _accepted)
        _qa_pdf_extraction(record, exceptions, metadata)
        _qa_llm_extraction(record, exceptions)

    _qa_duplicate_inclusion(records, exceptions)
    _qa_template_check(template_check, exceptions)
    return exceptions


def assert_final_runsheet_ready(
    records: list[SourceDocument],
    expected_document_count: int,
    template_check: TemplateCheckResult | dict[str, Any] | None = None,
) -> list[QAException]:
    exceptions = run_qa(
        records,
        expected_document_count=expected_document_count,
        template_check=template_check,
    )
    assert_no_hard_stops(exceptions)
    return exceptions


def assert_no_hard_stops(exceptions: list[QAException]) -> None:
    hard_stops = get_hard_stop_exceptions(exceptions)
    if hard_stops:
        raise QAHardStopError(hard_stops)


def get_hard_stop_exceptions(exceptions: list[QAException]) -> list[QAException]:
    return [exception for exception in exceptions if exception.severity == "ERROR"]


def _qa_record(record: SourceDocument, exceptions: list[QAException]) -> None:
    if not record.source_document_id:
        exceptions.append(
            QAException(
                severity="ERROR",
                code="MISSING_SOURCE_DOCUMENT_ID",
                message="Every row must have a source_document_id.",
                field="source_document_id",
            )
        )

    if not record.status:
        exceptions.append(
            QAException(
                severity="ERROR",
                code="MISSING_STATUS",
                message="Every row must have a classification status.",
                source_document_id=record.source_document_id,
                field="status",
            )
        )

    if record.status == ClassificationStatus.REDLINE and not record.redline_reason:
        exceptions.append(
            QAException(
                severity="ERROR",
                code="MISSING_REDLINE_REASON",
                message="Every REDLINE row must have redline_reason.",
                source_document_id=record.source_document_id,
                field="redline_reason",
            )
        )

    if record.status == ClassificationStatus.REVIEW and not record.review_question:
        exceptions.append(
            QAException(
                severity="ERROR",
                code="MISSING_REVIEW_QUESTION",
                message="Every REVIEW row must have review_question.",
                source_document_id=record.source_document_id,
                field="review_question",
            )
        )

    if (
        record.status != ClassificationStatus.REDLINE
        and _is_ogl_by_type(record)
        and not record.lease_status
    ):
        exceptions.append(
            QAException(
                severity="ERROR",
                code="MISSING_LEASE_STATUS",
                message="OGL record has no lease_status",
                source_document_id=record.source_document_id,
                field="lease_status",
            )
        )

    if record.status == ClassificationStatus.DUPLICATE and not record.duplicate_of:
        exceptions.append(
            QAException(
                severity="ERROR",
                code="DUPLICATE_WITHOUT_CANONICAL",
                message="DUPLICATE rows must identify duplicate_of.",
                source_document_id=record.source_document_id,
                field="duplicate_of",
            )
        )


def _qa_duplicate_inclusion(
    records: list[SourceDocument],
    exceptions: list[QAException],
) -> None:
    for record in records:
        if record.duplicate_of and record.status in {
            ClassificationStatus.INCLUDE_FULL,
            ClassificationStatus.INCLUDE_LIMITED,
        }:
            exceptions.append(
                QAException(
                    severity="ERROR",
                    code="DUPLICATE_INCLUDED",
                    message="A likely duplicate is included instead of marked DUPLICATE.",
                    source_document_id=record.source_document_id,
                    field="status",
                )
            )


def _qa_template_check(
    template_check: TemplateCheckResult | dict[str, Any] | None,
    exceptions: list[QAException],
) -> None:
    if template_check is None:
        return
    payload = (
        template_check.as_dict()
        if isinstance(template_check, TemplateCheckResult)
        else template_check
    )
    if not payload.get("passed"):
        exceptions.append(
            QAException(
                severity="ERROR",
                code="TEMPLATE_CHECK_FAILED",
                message=payload.get("message", "Template check failed."),
                field="template",
            )
        )


def _qa_source_verification(
    record: SourceDocument,
    exceptions: list[QAException],
    source_verification_required: bool,
    accepted_missing: set[str] | None = None,
) -> None:
    if not source_verification_required:
        return
    if record.status in {ClassificationStatus.REDLINE, ClassificationStatus.DUPLICATE}:
        return
    needs_source = record.status in {
        ClassificationStatus.INCLUDE_FULL,
        ClassificationStatus.INCLUDE_LIMITED,
        ClassificationStatus.REVIEW,
    } or is_oil_and_gas_lease(record)
    if needs_source and not record.matched_source_file:
        instr = record.instrument_number or ""
        if accepted_missing and instr and instr in accepted_missing:
            exceptions.append(
                QAException(
                    severity="WARNING",
                    code="SOURCE_FILE_NOT_MATCHED",
                    message=(
                        f"Source file absent for instrument {instr} — "
                        "absence acknowledged by analyst."
                    ),
                    source_document_id=record.source_document_id,
                    field="matched_source_file",
                )
            )
        else:
            exceptions.append(
                QAException(
                    severity="ERROR",
                    code="SOURCE_FILE_NOT_MATCHED",
                    message="Required source document was not matched to a package file.",
                    source_document_id=record.source_document_id,
                    field="matched_source_file",
                )
            )


def _qa_pdf_extraction(
    record: SourceDocument,
    exceptions: list[QAException],
    metadata: ProjectMetadata | dict[str, Any] | None,
) -> None:
    status = record.pdf_extraction_status
    if not status:
        return

    if status == EXTRACTION_ERROR:
        exceptions.append(
            QAException(
                severity="ERROR",
                code="PDF_EXTRACTION_ERROR",
                message="PDF extraction failed; source document cannot be read.",
                source_document_id=record.source_document_id,
                field="pdf_extraction_status",
            )
        )
        return

    if status == OCR_REQUIRED:
        exceptions.append(
            QAException(
                severity="WARNING",
                code="PDF_OCR_REQUIRED",
                message="PDF has no extractable text; OCR is required for verification.",
                source_document_id=record.source_document_id,
                field="pdf_extraction_status",
            )
        )

    if status == LOW_CONFIDENCE_TEXT:
        exceptions.append(
            QAException(
                severity="WARNING",
                code="PDF_LOW_CONFIDENCE",
                message=(
                    "PDF text extraction confidence is low; "
                    "do not rely on extracted fields without human review."
                ),
                source_document_id=record.source_document_id,
                field="pdf_extraction_status",
            )
        )

    if (
        record.possible_lease_primary_term_snippets
        and is_oil_and_gas_lease(record)
        and record.lease_status == LeaseStatus.REVIEW
    ):
        exceptions.append(
            QAException(
                severity="WARNING",
                code="POSSIBLE_LEASE_TERM_UNRESOLVED",
                message="Possible lease primary term found in PDF; confirm lease_status.",
                source_document_id=record.source_document_id,
                field="lease_status",
            )
        )

    if metadata and record.possible_legal_description_snippets:
        _qa_legal_description_snippets(record, exceptions, metadata)


def _qa_legal_description_snippets(
    record: SourceDocument,
    exceptions: list[QAException],
    metadata: ProjectMetadata | dict[str, Any],
) -> None:
    if isinstance(metadata, dict):
        section = metadata.get("section")
        township = metadata.get("township")
        range_ = metadata.get("range")
    else:
        section = metadata.section
        township = metadata.township
        range_ = metadata.range

    if not any([section, township, range_]):
        return

    combined = " ".join(record.possible_legal_description_snippets).lower()
    mismatches = []
    if section and section.lower() not in combined:
        mismatches.append(f"section {section}")
    if township and township.lower() not in combined:
        mismatches.append(f"township {township}")
    if range_ and range_.lower() not in combined:
        mismatches.append(f"range {range_}")

    if mismatches:
        exceptions.append(
            QAException(
                severity="WARNING",
                code="LEGAL_DESCRIPTION_SECTION_MISMATCH",
                message=f"Legal description snippets do not include: {', '.join(mismatches)}.",
                source_document_id=record.source_document_id,
                field="possible_legal_description_snippets",
            )
        )


def _qa_llm_extraction(
    record: SourceDocument,
    exceptions: list[QAException],
) -> None:
    if not record.llm_extraction_model:
        return

    error = record.source_trace.get("llm_extraction_error")
    if error:
        exceptions.append(
            QAException(
                severity="WARNING",
                code="LLM_EXTRACTION_FAILED",
                message=f"LLM extraction failed for this record; conveyance/comments may be missing. ({error})",
                source_document_id=record.source_document_id,
                field="llm_extraction",
            )
        )

    any_low = bool(record.source_trace.get("llm_low_confidence_fields"))
    if record.llm_conveyance_confidence is not None and record.llm_conveyance_confidence < 0.85:
        any_low = True
    if record.llm_comments_confidence is not None and record.llm_comments_confidence < 0.85:
        any_low = True

    if any_low:
        low_fields = record.source_trace.get("llm_low_confidence_fields") or []
        fields_desc = ", ".join(low_fields) if low_fields else "extracted field(s)"
        exceptions.append(
            QAException(
                severity="WARNING",
                code="LLM_EXTRACTION_LOW_CONFIDENCE",
                message=f"LLM extraction low confidence for {fields_desc}; verify manually.",
                source_document_id=record.source_document_id,
                field="conveyance",
            )
        )


def qa_to_dataframe(exceptions: list[QAException]) -> pd.DataFrame:
    rows = [model_to_dict(exception) for exception in exceptions]
    return pd.DataFrame(
        rows,
        columns=["severity", "code", "message", "source_document_id", "field"],
    )


def export_qa_exception_log(
    exceptions: list[QAException],
    output_path: str | Path,
) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    qa_to_dataframe(exceptions).to_excel(output_path, index=False)
    return output_path


def build_processing_summary(
    records: list[SourceDocument],
    exceptions: list[QAException],
    template_status: str,
    output_files: dict[str, str] | None = None,
) -> dict[str, Any]:
    statuses = [record.status for record in records]
    included = sum(
        status in {ClassificationStatus.INCLUDE_FULL, ClassificationStatus.INCLUDE_LIMITED}
        for status in statuses
    )
    return {
        "total_documents": len(records),
        "processed_documents": sum(status is not None for status in statuses),
        "included": included,
        "redlined": sum(status == ClassificationStatus.REDLINE for status in statuses),
        "review": sum(status == ClassificationStatus.REVIEW for status in statuses),
        "duplicates": sum(status == ClassificationStatus.DUPLICATE for status in statuses),
        "errors": sum(exception.severity == "ERROR" for exception in exceptions),
        "template_check_status": template_status,
        "output_files": output_files or {},
    }


def records_by_status(
    records: list[SourceDocument],
    status: ClassificationStatus,
) -> list[SourceDocument]:
    return [record for record in records if record.status == status]
