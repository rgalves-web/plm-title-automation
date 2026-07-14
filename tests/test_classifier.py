from datetime import date

from src.classifier import classify_document
from src.schemas import ClassificationStatus, LeaseStatus, SourceDocument


def make_record(document_type: str, **kwargs) -> SourceDocument:
    return SourceDocument(
        source_document_id=kwargs.pop("source_document_id", "DOC-000001"),
        source_row_number=2,
        document_type=document_type,
        **kwargs,
    )


def test_patent_is_included_full():
    record = classify_document(make_record("Patent"))
    assert record.status == ClassificationStatus.INCLUDE_FULL


def test_easement_is_redlined_with_reason():
    record = classify_document(make_record("Pipeline Easement"))
    assert record.status == ClassificationStatus.REDLINE
    assert record.redline_reason


def test_correction_deed_goes_to_review():
    record = classify_document(make_record("Correction Deed"))
    assert record.status == ClassificationStatus.REVIEW
    assert record.review_question


def test_expired_oil_and_gas_lease_is_included_and_marked_expired():
    record = classify_document(
        make_record(
            "Oil and Gas Lease",
            document_title="Oil and Gas Lease with 5 year primary term",
            instrument_date=date(1990, 1, 1),
        )
    )
    assert record.status == ClassificationStatus.INCLUDE_FULL
    assert record.lease_status == LeaseStatus.EXPIRED
    assert "EXPIRED" in record.comments


# ---------------------------------------------------------------------------
# Mechanism 1: LLM recovery restores INCLUDE_FULL after source-verification demotion
# ---------------------------------------------------------------------------

def test_llm_recovery_restores_include_full():
    from src.pipeline import _run_llm_recovery

    record = make_record("Mineral Deed")
    record.status = ClassificationStatus.REVIEW
    record.source_trace["pre_source_verification_status"] = "INCLUDE_FULL"
    record.source_trace["source_verification_demotion_reason"] = "EXTRACTION_ERROR"
    record.llm_conveyance_confidence = 0.90
    record.review_question = "Matched source file cannot be read."

    count = _run_llm_recovery([record])

    assert count == 1
    assert record.status == ClassificationStatus.INCLUDE_FULL
    assert record.review_question is None
    assert record.source_trace.get("reclassified_by") == "llm_extraction_recovery"


def test_llm_recovery_does_not_restore_without_high_confidence():
    from src.pipeline import _run_llm_recovery

    record = make_record("Mineral Deed")
    record.status = ClassificationStatus.REVIEW
    record.source_trace["pre_source_verification_status"] = "INCLUDE_FULL"
    record.source_trace["source_verification_demotion_reason"] = "EXTRACTION_ERROR"
    record.llm_conveyance_confidence = 0.70  # below 0.85

    count = _run_llm_recovery([record])

    assert count == 0
    assert record.status == ClassificationStatus.REVIEW


# ---------------------------------------------------------------------------
# Mechanism 3: lease_status refreshed from LLM-extracted comments
# ---------------------------------------------------------------------------

def test_lease_status_refreshed_from_llm_comments():
    from src.pipeline import _refresh_lease_status_post_llm

    record = make_record(
        "Oil and Gas Lease",
        instrument_date=date(2020, 1, 1),
    )
    record.status = ClassificationStatus.INCLUDE_FULL
    record.lease_status = None
    record.comments = "Primary Term: 5 years\nRoyalty: 1/6\nACTIVE"

    count = _refresh_lease_status_post_llm([record])

    assert count == 1
    assert record.lease_status == LeaseStatus.ACTIVE
    assert record.source_trace.get("lease_status_source") == "llm_post_extraction"


def test_lease_status_refresh_detects_expired_from_comments():
    from src.pipeline import _refresh_lease_status_post_llm

    record = make_record(
        "Oil and Gas Lease",
        instrument_date=date(2005, 1, 1),
    )
    record.status = ClassificationStatus.INCLUDE_FULL
    record.lease_status = None
    record.comments = "Primary Term: 5 years\nRoyalty: 1/8\nEXPIRED"

    count = _refresh_lease_status_post_llm([record])

    assert count == 1
    assert record.lease_status == LeaseStatus.EXPIRED
