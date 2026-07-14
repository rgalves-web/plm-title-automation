import pytest

from src.qa import QAHardStopError, assert_final_runsheet_ready, run_qa
from src.schemas import ClassificationStatus, LeaseStatus, SourceDocument


def _record(
    status=ClassificationStatus.INCLUDE_FULL,
    document_type="Patent",
    source_document_id="DOC-000001",
    **kwargs,
) -> SourceDocument:
    return SourceDocument(
        source_document_id=source_document_id,
        source_row_number=2,
        document_type=document_type,
        status=status,
        **kwargs,
    )


def _assert_blocks_with(records, expected_document_count, code):
    with pytest.raises(QAHardStopError) as raised:
        assert_final_runsheet_ready(records, expected_document_count)
    assert any(exception.code == code for exception in raised.value.exceptions)


def test_document_count_mismatch_blocks_final_runsheet_export():
    _assert_blocks_with([_record()], expected_document_count=2, code="DOCUMENT_COUNT_MISMATCH")


def test_missing_status_blocks_final_runsheet_export():
    _assert_blocks_with(
        [_record(status=None)],
        expected_document_count=1,
        code="MISSING_STATUS",
    )


def test_redline_without_reason_blocks_final_runsheet_export():
    _assert_blocks_with(
        [_record(status=ClassificationStatus.REDLINE, document_type="Easement")],
        expected_document_count=1,
        code="MISSING_REDLINE_REASON",
    )


def test_review_without_question_blocks_final_runsheet_export():
    _assert_blocks_with(
        [_record(status=ClassificationStatus.REVIEW, document_type="Correction Deed")],
        expected_document_count=1,
        code="MISSING_REVIEW_QUESTION",
    )


def test_oil_and_gas_lease_without_lease_status_blocks_final_runsheet_export():
    _assert_blocks_with(
        [_record(document_type="Oil and Gas Lease")],
        expected_document_count=1,
        code="MISSING_LEASE_STATUS",
    )


def test_valid_required_fields_allow_final_runsheet_export():
    exceptions = assert_final_runsheet_ready(
        [
            _record(),
            _record(
                source_document_id="DOC-000002",
                status=ClassificationStatus.REDLINE,
                document_type="Easement",
                redline_reason="Non-title easement.",
            ),
            _record(
                source_document_id="DOC-000003",
                status=ClassificationStatus.REVIEW,
                document_type="Correction Deed",
                review_question="Confirm title effect.",
            ),
            _record(
                source_document_id="DOC-000004",
                document_type="Oil and Gas Lease",
                lease_status=LeaseStatus.EXPIRED,
            ),
        ],
        expected_document_count=4,
    )
    assert exceptions == []


def test_redline_without_reason_is_qa_error():
    record = SourceDocument(
        source_document_id="DOC-000001",
        source_row_number=2,
        document_type="Easement",
        status=ClassificationStatus.REDLINE,
    )
    exceptions = run_qa([record], expected_document_count=1)
    assert any(exception.code == "MISSING_REDLINE_REASON" for exception in exceptions)


def test_template_failure_is_qa_error():
    record = SourceDocument(
        source_document_id="DOC-000001",
        source_row_number=2,
        document_type="Patent",
        status=ClassificationStatus.INCLUDE_FULL,
    )
    exceptions = run_qa(
        [record],
        expected_document_count=1,
        template_check={"passed": False, "message": "Missing Source Document ID"},
    )
    assert any(exception.code == "TEMPLATE_CHECK_FAILED" for exception in exceptions)


# ---------------------------------------------------------------------------
# accepted_missing_sources downgrades SOURCE_FILE_NOT_MATCHED to WARNING
# ---------------------------------------------------------------------------

def test_accepted_missing_sources_downgrades_error_to_warning():
    record = SourceDocument(
        source_document_id="DOC-000001",
        source_row_number=2,
        document_type="Mineral Deed",
        instrument_number="12345",
        status=ClassificationStatus.INCLUDE_FULL,
    )
    # Without accepted list → ERROR
    errs = run_qa(
        [record],
        expected_document_count=1,
        source_verification_required=True,
    )
    error_codes = [e for e in errs if e.code == "SOURCE_FILE_NOT_MATCHED"]
    assert len(error_codes) == 1
    assert error_codes[0].severity == "ERROR"

    # With accepted list containing the instrument number → WARNING
    warns = run_qa(
        [record],
        expected_document_count=1,
        source_verification_required=True,
        accepted_missing_sources=["12345"],
    )
    warn_codes = [e for e in warns if e.code == "SOURCE_FILE_NOT_MATCHED"]
    assert len(warn_codes) == 1
    assert warn_codes[0].severity == "WARNING"
    assert "acknowledged" in warn_codes[0].message
