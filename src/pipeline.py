from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from src.classifier import classify_documents
from src.dedupe import deduplicate_documents
from src.document_register import (
    create_document_register,
    export_document_register,
    records_to_dataframe,
)
from src.excel_writer import generate_runsheet_with_report, load_template_config, validate_template
from src.ownership import OwnershipResult, run_ownership_analysis
from src.intake import read_document_list
from src.lease_engine import infer_lease_status, is_oil_and_gas_lease
from src.pdf_reader import (
    EXTRACTION_ERROR,
    LOW_CONFIDENCE_TEXT,
    OCR_REQUIRED,
    PDFExtractionResult,
    TEXT_EXTRACTED,
    apply_extraction_to_record,
    extract_document,
)
from src.qa import (
    assert_no_hard_stops,
    build_processing_summary,
    export_qa_exception_log,
    records_by_status,
    run_qa,
)
from src.schemas import ClassificationStatus, ProjectMetadata, QAException, SourceDocument
from src.source_matcher import (
    match_source_files,
    materialize_matched_source_file,
    requires_source_reading,
)
import time as _time

from src.utils import get_logger, safe_filename, timestamp, write_json

logger = get_logger(__name__)

# Shared OCR cache — persists across runs so Tesseract never re-processes a PDF
# that was already extracted. The key is the PDF filename stem, written by pdf_reader.
_OCR_CACHE_DIR = Path("data/output/ocr_cache")


@dataclass
class PipelineResult:
    output_dir: Path
    records: list[SourceDocument]
    qa_exceptions: list[QAException]
    summary: dict[str, Any]
    artifacts: dict[str, Path] = field(default_factory=dict)


def run_full_pipeline(
    document_list_path: str | Path,
    template_path: str | Path,
    metadata: ProjectMetadata | dict[str, Any],
    output_root: str | Path = "data/output",
    column_mapping: dict[str, str] | None = None,
    document_package_path: str | Path | None = None,
    extracted_document_folder: str | Path | None = None,
) -> PipelineResult:
    dataframe = read_document_list(document_list_path)
    return run_full_pipeline_from_dataframe(
        dataframe=dataframe,
        template_path=template_path,
        metadata=metadata,
        output_root=output_root,
        column_mapping=column_mapping,
        source_file_name=Path(document_list_path).name,
        document_package_path=document_package_path,
        extracted_document_folder=extracted_document_folder,
    )


def run_full_pipeline_from_dataframe(
    dataframe: pd.DataFrame,
    template_path: str | Path,
    metadata: ProjectMetadata | dict[str, Any],
    output_root: str | Path = "data/output",
    column_mapping: dict[str, str] | None = None,
    source_file_name: str | None = None,
    document_package_path: str | Path | None = None,
    extracted_document_folder: str | Path | None = None,
    llm_extraction: bool = False,
) -> PipelineResult:
    if isinstance(metadata, dict):
        metadata = ProjectMetadata(**metadata)

    _pipeline_start = _time.monotonic()

    output_dir = (
        Path(output_root)
        / f"{safe_filename(metadata.project_name)}_{safe_filename(metadata.county)}_{timestamp()}"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    records = create_document_register(
        dataframe,
        column_mapping=column_mapping,
        metadata=metadata,
        source_file_name=source_file_name,
    )
    deduplicate_documents(records)
    classify_documents(records)

    source_verification_required = bool(document_package_path or extracted_document_folder)
    source_metrics: dict[str, Any] = {}
    if source_verification_required:
        source_metrics = run_source_verification(
            records,
            output_dir=output_dir,
            metadata=metadata,
            document_package_path=document_package_path,
            extracted_document_folder=extracted_document_folder,
        )

    llm_metrics: dict[str, Any] = {}
    if llm_extraction:
        llm_metrics = run_llm_extraction(records, output_dir=output_dir, metadata=metadata)
        llm_metrics["recovery_count"] = _run_llm_recovery(records)
        llm_metrics["lease_status_updated"] = _refresh_lease_status_post_llm(records)

    ownership_result: OwnershipResult | None = None
    ownership_metrics: dict[str, Any] = {}
    try:
        ownership_result, ownership_metrics = run_ownership_analysis(
            records, output_dir=output_dir, metadata=metadata
        )
    except Exception as exc:
        logger.warning("Ownership analysis failed: %s", exc)

    artifacts: dict[str, Path] = {}
    artifacts["document_register"] = export_document_register(
        records, output_dir / "document_register.xlsx", include_raw=True
    )
    artifacts["classification_results"] = _export_records(
        records, output_dir / "classification_results.xlsx"
    )
    artifacts["redline_rows"] = _export_status_rows(
        records, ClassificationStatus.REDLINE, output_dir / "redline_rows.xlsx"
    )
    artifacts["review_required"] = _export_status_rows(
        records, ClassificationStatus.REVIEW, output_dir / "review_required.xlsx"
    )

    template_check = validate_template(template_path)
    _tmpl_config = load_template_config()
    _accepted_missing = _tmpl_config.get("accepted_missing_sources") or []
    qa_exceptions = run_qa(
        records,
        expected_document_count=len(dataframe),
        template_check=template_check,
        source_verification_required=source_verification_required,
        metadata=metadata,
        accepted_missing_sources=_accepted_missing,
    )
    artifacts["review_checklist"] = export_review_checklist(
        records,
        qa_exceptions,
        output_dir / "10_review_checklist.xlsx",
    )
    artifacts["source_match_report"] = export_source_verification_report(
        records,
        qa_exceptions,
        output_dir / "08_source_match_report.xlsx",
        report_type="source_match",
    )
    artifacts["pdf_extraction_report"] = export_source_verification_report(
        records,
        qa_exceptions,
        output_dir / "09_pdf_extraction_report.xlsx",
        report_type="pdf_extraction",
    )
    artifacts["extraction_coverage"] = output_dir / "extraction_coverage.json"
    write_json(
        artifacts["extraction_coverage"],
        build_extraction_coverage(records),
    )
    artifacts["qa_exception_log"] = export_qa_exception_log(
        qa_exceptions, output_dir / "QA_EXCEPTION_LOG.xlsx"
    )
    artifacts["processing_summary"] = output_dir / "processing_summary.json"
    summary = build_processing_summary(
        records,
        qa_exceptions,
        template_status="PASS" if template_check.passed else "FAIL",
        output_files={name: str(path) for name, path in artifacts.items()},
    )
    summary["source_verification"] = source_metrics
    summary["llm_extraction"] = llm_metrics
    write_json(artifacts["processing_summary"], summary)
    assert_no_hard_stops(qa_exceptions)

    runsheet_result = generate_runsheet_with_report(
        template_path,
        records,
        output_dir,
        project_name=metadata.project_name,
        metadata=metadata,
        ownership_result=ownership_result,
    )
    artifacts["preliminary_runsheet"] = runsheet_result.output_path
    artifacts["template_integrity_report"] = runsheet_result.integrity_report_path
    summary = build_processing_summary(
        records,
        qa_exceptions,
        template_status="PASS" if template_check.passed else "FAIL",
        output_files={name: str(path) for name, path in artifacts.items()},
    )
    summary["source_verification"] = source_metrics
    summary["llm_extraction"] = llm_metrics
    summary["ownership"] = ownership_metrics
    completion = _build_completion_block(
        records, qa_exceptions, _time.monotonic() - _pipeline_start
    )
    summary["completion"] = completion
    write_json(artifacts["processing_summary"], summary)
    _print_completion(completion, output_dir)

    return PipelineResult(
        output_dir=output_dir,
        records=records,
        qa_exceptions=qa_exceptions,
        summary=summary,
        artifacts=artifacts,
    )


def _export_status_rows(
    records: list[SourceDocument],
    status: ClassificationStatus,
    output_path: Path,
) -> Path:
    rows = records_by_status(records, status)
    return _export_records(rows, output_path)


def _export_records(records: list[SourceDocument], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    records_to_dataframe(records).to_excel(output_path, index=False)
    return output_path


def run_source_verification(
    records: list[SourceDocument],
    output_dir: str | Path,
    metadata: ProjectMetadata | dict[str, Any] | None = None,
    document_package_path: str | Path | None = None,
    extracted_document_folder: str | Path | None = None,
) -> dict[str, Any]:
    if isinstance(metadata, dict):
        metadata = ProjectMetadata(**metadata)

    qa_internal_dir = Path(output_dir) / "QA_internal"
    source_files_dir = qa_internal_dir / "source_files"

    # Use a shared persistent cache so OCR is never repeated across runs.
    # Both the raw _ocr.txt files (Tesseract output) and the per-record .txt
    # files (LLM input) land here. record.extracted_text_path points into this dir.
    ocr_cache_dir = _OCR_CACHE_DIR
    ocr_cache_dir.mkdir(parents=True, exist_ok=True)

    match_source_files(
        records,
        document_package_path=document_package_path,
        extracted_document_folder=extracted_document_folder,
    )

    for record in records:
        if not requires_source_reading(record):
            continue
        if not record.matched_source_file:
            continue
        source_path = materialize_matched_source_file(record, source_files_dir)
        if not source_path or not source_path.exists():
            _mark_extraction_error(
                record,
                "Matched source file could not be materialized for reading.",
            )
            continue
        try:
            extraction = extract_document(source_path, text_cache_dir=ocr_cache_dir)
        except Exception as exc:
            extraction = PDFExtractionResult(
                file_path=str(source_path),
                page_count=0,
                extraction_status=EXTRACTION_ERROR,
                extraction_confidence=0.0,
                extraction_engine="source_verification",
                review_required=True,
                review_reason="Matched source file cannot be read; human review is required.",
                error=str(exc),
            )
        apply_extraction_to_record(record, extraction, ocr_cache_dir)
        _refresh_lease_status_from_extraction(record, extraction)

    return build_source_verification_metrics(records)


def _mark_extraction_error(record: SourceDocument, message: str) -> None:
    record.pdf_extraction_status = EXTRACTION_ERROR
    record.pdf_extraction_confidence = 0.0
    record.source_trace["pdf_extraction_error"] = message
    if record.status not in (ClassificationStatus.DUPLICATE, ClassificationStatus.REVIEW):
        record.source_trace["pre_source_verification_status"] = record.status.value
        record.source_trace["source_verification_demotion_reason"] = "EXTRACTION_ERROR"
    if record.status != ClassificationStatus.DUPLICATE:
        record.status = ClassificationStatus.REVIEW
    record.review_question = _append_review_question(record.review_question, message)


def _refresh_lease_status_from_extraction(
    record: SourceDocument,
    extraction: PDFExtractionResult,
) -> None:
    if not is_oil_and_gas_lease(record):
        return
    extracted_status = extraction.extracted_fields.get("lease_status")
    if extracted_status:
        return
    if (
        extraction.possible_lease_primary_term_snippets
        and not record.lease_status
        and record.status != ClassificationStatus.DUPLICATE
    ):
        if record.status != ClassificationStatus.REVIEW:
            record.source_trace["pre_source_verification_status"] = record.status.value
            record.source_trace["source_verification_demotion_reason"] = "POSSIBLE_LEASE_TERM"
        record.status = ClassificationStatus.REVIEW
        record.review_question = _append_review_question(
            record.review_question,
            "Possible lease primary term found in PDF; confirm lease_status.",
        )


_LLM_ELIGIBLE_STATUSES = {
    ClassificationStatus.INCLUDE_FULL,
    ClassificationStatus.INCLUDE_LIMITED,
    ClassificationStatus.REVIEW,
}


def run_llm_extraction(
    records: list[SourceDocument],
    output_dir: str | Path,
    metadata: ProjectMetadata | dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run Claude structured extraction on all records that have OCR text.

    Does NOT touch REDLINE or DUPLICATE rows.
    Cross-reference detection runs as a second pass after all individual extractions.
    """
    from src.llm_extractor import (  # lazy import — anthropic is optional
        LLMConfigError,
        apply_instrument_effect_reclassification,
        apply_llm_extraction_to_record,
        extract_fields_for_record,
    )

    if isinstance(metadata, dict):
        metadata = ProjectMetadata(**metadata)

    qa_internal_dir = Path(output_dir) / "QA_internal"
    llm_cache_dir = qa_internal_dir / "llm_cache"

    eligible = [
        r for r in records
        if r.status in _LLM_ELIGIBLE_STATUSES
        and r.pdf_extraction_status == TEXT_EXTRACTED
        and r.extracted_text_path
        and Path(r.extracted_text_path).exists()
    ]

    metrics: dict[str, Any] = {
        "total_eligible": len(eligible),
        "extracted_successfully": 0,
        "extraction_errors": 0,
        "low_confidence": 0,
        "cross_references_found": 0,
        "reclassified_to_include": 0,
        "reclassified_to_redline": 0,
        "prompt_tokens_total": 0,
        "completion_tokens_total": 0,
    }

    # Attach project metadata to source_trace so the prompt can use section/township/range
    if metadata:
        meta_dict = {
            "section": metadata.section,
            "township": metadata.township,
            "range": metadata.range,
        }
        for r in eligible:
            r.source_trace.setdefault("project_metadata", meta_dict)

    for record in eligible:
        try:
            ocr_text = Path(record.extracted_text_path).read_text(encoding="utf-8")
        except Exception as exc:
            logger.warning("Cannot read OCR text for %s: %s", record.source_document_id, exc)
            continue

        if not ocr_text.strip():
            continue

        try:
            result = extract_fields_for_record(record, ocr_text, cache_dir=llm_cache_dir)
        except LLMConfigError:
            raise
        except Exception as exc:
            logger.warning("LLM call failed for %s: %s", record.source_document_id, exc)
            metrics["extraction_errors"] += 1
            continue

        qa_codes = apply_llm_extraction_to_record(record, result)
        metrics["prompt_tokens_total"] += result.prompt_tokens
        metrics["completion_tokens_total"] += result.completion_tokens

        if result.error:
            metrics["extraction_errors"] += 1
        else:
            metrics["extracted_successfully"] += 1

        if "LLM_EXTRACTION_LOW_CONFIDENCE" in qa_codes:
            metrics["low_confidence"] += 1

        # Mechanism 2: reclassify uncertain assignments/bills of sale
        effect_tag = apply_instrument_effect_reclassification(record, result)
        if effect_tag == "include":
            metrics["reclassified_to_include"] += 1
        elif effect_tag == "redline":
            metrics["reclassified_to_redline"] += 1

    metrics["cross_references_found"] = _run_cross_reference_detection(records)
    return metrics


def _run_llm_recovery(records: list[SourceDocument]) -> int:
    """Mechanism 1: restore INCLUDE status for records demoted only by source verification.

    A record is eligible when:
    - Current status is REVIEW
    - pre_source_verification_status was INCLUDE_FULL or INCLUDE_LIMITED
    - source_verification_demotion_reason is set (any OCR/extraction failure)
    - LLM extracted conveyance with confidence >= HIGH_CONFIDENCE (0.85)

    Returns the number of records restored.
    """
    from src.llm_extractor import HIGH_CONFIDENCE

    restored = 0
    for record in records:
        if record.status != ClassificationStatus.REVIEW:
            continue
        original_str = record.source_trace.get("pre_source_verification_status")
        if original_str not in ("INCLUDE_FULL", "INCLUDE_LIMITED"):
            continue
        if not record.source_trace.get("source_verification_demotion_reason"):
            continue
        if (
            record.llm_conveyance_confidence is None
            or record.llm_conveyance_confidence < HIGH_CONFIDENCE
        ):
            continue
        record.status = ClassificationStatus(original_str)
        record.source_trace["reclassified_by"] = "llm_extraction_recovery"
        record.source_trace["original_demotion_reason"] = record.source_trace[
            "source_verification_demotion_reason"
        ]
        record.review_question = None
        logger.info(
            "LLM recovery: %s restored to %s (demotion: %s)",
            record.source_document_id,
            original_str,
            record.source_trace["original_demotion_reason"],
        )
        restored += 1
    return restored


def _refresh_lease_status_post_llm(records: list[SourceDocument]) -> int:
    """Mechanism 3: re-infer lease_status using LLM-extracted conveyance/comments text.

    Runs after LLM extraction so "Primary Term: N years" and ACTIVE/EXPIRED/RELEASED
    written by the LLM into comments are available for inference.

    Returns the number of records updated.
    """
    updated = 0
    for record in records:
        if not is_oil_and_gas_lease(record):
            continue
        from src.schemas import LeaseStatus as _LS
        if record.lease_status not in (None, _LS.REVIEW):
            continue
        llm_text = " ".join(filter(None, [record.conveyance, record.comments]))
        if not llm_text.strip():
            continue
        new_status = infer_lease_status(record, extracted_text=llm_text)
        if new_status and new_status != _LS.REVIEW:
            record.lease_status = new_status
            record.source_trace["lease_status_source"] = "llm_post_extraction"
            if new_status == _LS.ACTIVE:
                record.source_trace["lease_status_needs_review"] = True
            logger.info(
                "Post-LLM lease status: %s -> %s",
                record.source_document_id, new_status.value,
            )
            updated += 1
    return updated


def _run_cross_reference_detection(records: list[SourceDocument]) -> int:
    """Scan OCR text for book/page/reception mentions and append *See cross-refs.

    Runs after all per-record LLM extractions so the full index is available.
    Never overwrites existing comments — only appends unique *See lines.
    """
    import re as _re

    SKIP = {ClassificationStatus.REDLINE, ClassificationStatus.DUPLICATE}

    by_instrument: dict[str, SourceDocument] = {}
    by_book_page: dict[tuple[str, str], SourceDocument] = {}
    for r in records:
        if r.status in SKIP:
            continue
        if r.instrument_number:
            key = _re.sub(r"[^0-9A-Za-z]", "", r.instrument_number).upper()
            if key and key not in by_instrument:
                by_instrument[key] = r
        if r.book and r.page:
            bk = _re.sub(r"[^0-9]", "", str(r.book))
            pg = _re.sub(r"[^0-9]", "", str(r.page))
            if bk and pg:
                by_book_page[(bk, pg)] = r

    BOOK_PAGE_RE = _re.compile(
        r"\bbook\s+(\d+)[,\s]+page\s+(\d+)\b", _re.IGNORECASE
    )
    RECEPTION_RE = _re.compile(
        r"\breception\s*(?:no\.?|number|#)?\s*[:\s]?\s*([A-Z0-9]{5,20})\b",
        _re.IGNORECASE,
    )

    n_added = 0
    for record in records:
        if record.status in SKIP:
            continue

        ocr_text = ""
        if record.extracted_text_path:
            try:
                p = Path(record.extracted_text_path)
                if p.exists():
                    ocr_text = p.read_text(encoding="utf-8")
            except Exception:
                pass
        if not ocr_text:
            ocr_text = record.pdf_text_preview or ""
        if not ocr_text:
            continue

        found: set[str] = set()

        for m in BOOK_PAGE_RE.finditer(ocr_text):
            bk = _re.sub(r"[^0-9]", "", m.group(1))
            pg = _re.sub(r"[^0-9]", "", m.group(2))
            ref = by_book_page.get((bk, pg))
            if ref and ref.source_document_id != record.source_document_id:
                label = ref.instrument_number or f"Book {bk} Page {pg}"
                found.add(f"*See {ref.document_type or 'Instrument'} {label}")

        for m in RECEPTION_RE.finditer(ocr_text):
            num = _re.sub(r"[^0-9A-Za-z]", "", m.group(1)).upper()
            ref = by_instrument.get(num)
            if ref and ref.source_document_id != record.source_document_id:
                found.add(f"*See {ref.document_type or 'Instrument'} {ref.instrument_number or num}")

        if not found:
            continue

        refs_str = "\n".join(sorted(found))
        existing = record.comments or ""
        if refs_str not in existing:
            record.comments = (existing + "\n" + refs_str).strip() if existing else refs_str
            n_added += len(found)

    return n_added


def build_source_verification_metrics(records: list[SourceDocument]) -> dict[str, Any]:
    target_records = [record for record in records if requires_source_reading(record)]
    statuses = [record.pdf_extraction_status for record in records]
    return {
        "total_records": len(records),
        "records_requiring_source_verification": len(target_records),
        "matched_source_files": sum(bool(record.matched_source_file) for record in records),
        "unmatched_source_files": sum(
            requires_source_reading(record) and not record.matched_source_file
            for record in records
        ),
        "pdfs_read_successfully": sum(status == TEXT_EXTRACTED for status in statuses),
        "ocr_required": sum(status == OCR_REQUIRED for status in statuses),
        "low_confidence": sum(status == LOW_CONFIDENCE_TEXT for status in statuses),
        "extraction_errors": sum(status == EXTRACTION_ERROR for status in statuses),
        "review_count": sum(record.status == ClassificationStatus.REVIEW for record in records),
    }


_REVIEW_STATUSES = {
    ClassificationStatus.REVIEW,
    ClassificationStatus.INCLUDE_FULL,
    ClassificationStatus.INCLUDE_LIMITED,
}
_EXTRACTION_ATTENTION_STATUSES = {
    "LOW_CONFIDENCE_TEXT",
    "OCR_REQUIRED",
    "EXTRACTION_ERROR",
}


def export_review_checklist(
    records: list[SourceDocument],
    qa_exceptions: list[QAException],
    output_path: str | Path,
) -> Path:
    """10_review_checklist.xlsx — all rows needing human attention with source paths."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    attention_rows: list[dict] = []
    for record in records:
        needs_review = record.status == ClassificationStatus.REVIEW
        needs_extraction_review = (
            record.status in _REVIEW_STATUSES
            and record.pdf_extraction_status in _EXTRACTION_ATTENTION_STATUSES
        )
        if not (needs_review or needs_extraction_review):
            continue
        source_path = (
            record.source_trace.get("matched_source_path")
            or record.matched_source_file
            or "not matched"
        )
        attention_rows.append(
            {
                "row": record.source_row_number,
                "status": _value(record.status),
                "document_type": record.document_type,
                "instrument_number": record.instrument_number,
                "book": record.book,
                "page": record.page,
                "grantor": record.grantor,
                "grantee": record.grantee,
                "review_question": record.review_question,
                "source_file_path": source_path,
                "pdf_extraction_status": record.pdf_extraction_status,
                "ocr_text_preview": (record.pdf_text_preview or "")[:300],
            }
        )

    review_df = pd.DataFrame(
        attention_rows,
        columns=[
            "row",
            "status",
            "document_type",
            "instrument_number",
            "book",
            "page",
            "grantor",
            "grantee",
            "review_question",
            "source_file_path",
            "pdf_extraction_status",
            "ocr_text_preview",
        ],
    )
    qa_df = pd.DataFrame(
        [
            {
                "severity": e.severity,
                "code": e.code,
                "message": e.message,
                "document_id": e.source_document_id,
                "field": e.field,
            }
            for e in qa_exceptions
        ]
    )

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        review_df.to_excel(writer, sheet_name="Review Queue", index=False)
        qa_df.to_excel(writer, sheet_name="QA Exceptions", index=False)

    return output_path


SOURCE_VERIFICATION_REPORT_COLUMNS = [
    "source_document_id",
    "source_row_number",
    "document_type",
    "instrument_number",
    "book",
    "page",
    "grantor",
    "grantee",
    "status",
    "matched_source_file",
    "source_match_confidence",
    "source_match_method",
    "pdf_extraction_status",
    "pdf_extraction_confidence",
    "pdf_page_count",
    "pdf_text_preview",
    "possible_document_type_keywords",
    "possible_legal_description_snippets",
    "possible_lease_primary_term_snippets",
    "review_question",
    "qa_exception_codes",
]


def export_source_verification_report(
    records: list[SourceDocument],
    qa_exceptions: list[QAException],
    output_path: str | Path,
    report_type: str = "source_match",
) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    qa_codes_by_id = _qa_codes_by_source_document_id(qa_exceptions)
    rows = []
    for record in records:
        row = _source_verification_report_row(record, qa_codes_by_id)
        row["report_type"] = report_type
        rows.append(row)
    columns = SOURCE_VERIFICATION_REPORT_COLUMNS + ["report_type"]
    pd.DataFrame(rows, columns=columns).to_excel(output_path, index=False)
    return output_path


def build_extraction_coverage(records: list[SourceDocument]) -> dict[str, Any]:
    include_records = [
        record
        for record in records
        if record.status
        in {
            ClassificationStatus.INCLUDE_FULL,
            ClassificationStatus.INCLUDE_LIMITED,
            ClassificationStatus.REVIEW,
        }
    ]
    field_counts = {
        "conveyance_from_pdf": 0,
        "lands_from_pdf": 0,
        "effective_date_from_pdf": 0,
        "conveyance_from_llm": 0,
        "comments_from_llm": 0,
    }
    for record in include_records:
        populated = record.source_trace.get("pdf_populated_fields", {})
        if populated.get("conveyance"):
            field_counts["conveyance_from_pdf"] += 1
        if populated.get("legal_description"):
            field_counts["lands_from_pdf"] += 1
        if populated.get("effective_date"):
            field_counts["effective_date_from_pdf"] += 1
        if record.llm_conveyance_confidence is not None:
            field_counts["conveyance_from_llm"] += 1
        if record.llm_comments_confidence is not None:
            field_counts["comments_from_llm"] += 1

    denominator = len(include_records)
    percentages: dict[str, float] = {}
    for key, value in field_counts.items():
        if "_from_pdf" in key:
            pct_key = key.replace("_from_pdf", "_pdf_pct")
        else:
            pct_key = key.replace("_from_llm", "_llm_pct")
        percentages[pct_key] = _percentage(value, denominator)

    return {
        "include_rows_counted": denominator,
        **field_counts,
        **percentages,
    }


def _source_verification_report_row(
    record: SourceDocument,
    qa_codes_by_id: dict[str, list[str]],
) -> dict[str, Any]:
    return {
        "source_document_id": record.source_document_id,
        "source_row_number": record.source_row_number,
        "document_type": record.document_type,
        "instrument_number": record.instrument_number,
        "book": record.book,
        "page": record.page,
        "grantor": record.grantor,
        "grantee": record.grantee,
        "status": _value(record.status),
        "matched_source_file": record.matched_source_file,
        "source_match_confidence": record.source_match_confidence,
        "source_match_method": record.source_match_method,
        "pdf_extraction_status": record.pdf_extraction_status,
        "pdf_extraction_confidence": record.pdf_extraction_confidence,
        "pdf_page_count": record.pdf_page_count,
        "pdf_text_preview": record.pdf_text_preview,
        "possible_document_type_keywords": _join_values(record.possible_document_type_keywords),
        "possible_legal_description_snippets": _join_values(
            record.possible_legal_description_snippets
        ),
        "possible_lease_primary_term_snippets": _join_values(
            record.possible_lease_primary_term_snippets
        ),
        "review_question": record.review_question,
        "qa_exception_codes": " | ".join(
            qa_codes_by_id.get(record.source_document_id, [])
        ),
    }


def _qa_codes_by_source_document_id(
    exceptions: list[QAException],
) -> dict[str, list[str]]:
    codes: dict[str, list[str]] = {}
    for exception in exceptions:
        if exception.source_document_id:
            codes.setdefault(exception.source_document_id, []).append(exception.code)
    return codes


def _join_values(values: list[Any]) -> str:
    return " | ".join(str(value) for value in values if value not in (None, ""))


def _value(value: Any) -> Any:
    return getattr(value, "value", value)


def _percentage(value: int, denominator: int) -> float:
    if not denominator:
        return 0.0
    return round((value / denominator) * 100, 2)


def _build_completion_block(
    records: list[SourceDocument],
    qa_exceptions: list[QAException],
    elapsed_seconds: float,
) -> dict[str, Any]:
    include_records = [
        r for r in records
        if r.status in {ClassificationStatus.INCLUDE_FULL, ClassificationStatus.INCLUDE_LIMITED}
    ]
    n = len(include_records)
    n_conveyance = sum(1 for r in include_records if r.conveyance)
    n_comments = sum(1 for r in include_records if r.comments)
    return {
        "total_processed": len(records),
        "include_rows": n,
        "include_with_conveyance": n_conveyance,
        "include_with_comments": n_comments,
        "conveyance_pct": round(n_conveyance / n * 100, 1) if n else 0.0,
        "comments_pct": round(n_comments / n * 100, 1) if n else 0.0,
        "qa_errors": sum(e.severity == "ERROR" for e in qa_exceptions),
        "elapsed_seconds": round(elapsed_seconds, 1),
    }


def _print_completion(completion: dict[str, Any], output_dir: Path) -> None:
    n = completion["include_rows"]
    lines = [
        "",
        "=== PLM Pipeline Complete ===",
        f"  Processed : {completion['total_processed']} documents",
        f"  INCLUDE   : {n} rows",
        f"  CONVEYANCE: {completion['conveyance_pct']}%  ({completion['include_with_conveyance']}/{n} filled)",
        f"  COMMENTS  : {completion['comments_pct']}%  ({completion['include_with_comments']}/{n} filled)",
        f"  QA errors : {completion['qa_errors']}",
        f"  Elapsed   : {completion['elapsed_seconds']}s",
        f"  Output    : {output_dir}",
        "=============================",
        "",
    ]
    print("\n".join(lines))


def _append_review_question(existing: str | None, addition: str) -> str:
    existing = str(existing).strip() if existing else ""
    if not existing:
        return addition
    if addition in existing:
        return existing
    return f"{existing} {addition}"
