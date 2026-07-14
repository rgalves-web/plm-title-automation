"""Tests for src/llm_extractor.py — all API calls are mocked."""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.llm_extractor import (
    HIGH_CONFIDENCE,
    LOW_CONFIDENCE_THRESHOLD,
    LLMConfigError,
    LLMExtractionResult,
    LLMFieldResult,
    apply_instrument_effect_reclassification,
    apply_llm_extraction_to_record,
    extract_fields_for_record,
)
from src.schemas import ClassificationStatus, SourceDocument


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _record(**kwargs) -> SourceDocument:
    defaults = dict(
        source_document_id="DOC-000001",
        source_row_number=1,
        document_type="Patent",
        status=ClassificationStatus.INCLUDE_FULL,
    )
    defaults.update(kwargs)
    return SourceDocument(**defaults)


def _mock_response(conveyance_value: str, comments_value: str, confidence: float = 0.95):
    """Build a mock Anthropic messages.create() response with a tool_use block."""
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.input = {
        "conveyance": {
            "value": conveyance_value,
            "confidence": confidence,
            "provenance": "first paragraph of OCR text",
        },
        "comments": {
            "value": comments_value,
            "confidence": confidence,
            "provenance": "body of OCR text",
        },
    }
    usage = MagicMock()
    usage.input_tokens = 150
    usage.output_tokens = 80
    response = MagicMock()
    response.content = [tool_block]
    response.usage = usage
    return response


def _mock_response_with_parties(
    grantor_exact_value: str,
    grantee_exact_value: str,
    confidence: float = 0.92,
):
    """Mock response that includes grantor_exact and grantee_exact fields."""
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.input = {
        "conveyance": {"value": "ARTI to:\n\nSection 15", "confidence": 0.90},
        "comments": {"value": "", "confidence": 0.90},
        "grantor_exact": {"value": grantor_exact_value, "confidence": confidence,
                          "provenance": "granting clause"},
        "grantee_exact": {"value": grantee_exact_value, "confidence": confidence,
                          "provenance": "habendum clause"},
    }
    usage = MagicMock()
    usage.input_tokens = 160
    usage.output_tokens = 90
    response = MagicMock()
    response.content = [tool_block]
    response.usage = usage
    return response


def _call_extract(
    record: SourceDocument,
    ocr_text: str = "Sample OCR text with sufficient content.",
    cache_dir: Path | None = None,
    mock_return=None,
) -> LLMExtractionResult:
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-sk-key"}):
        with patch("anthropic.Anthropic") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create.return_value = mock_return or _mock_response(
                "Grant of:\n\nSection 15,\nTownship 4S, Range 64W,\n6th P.M., Arapahoe County, Colorado",
                "",
            )
            return extract_fields_for_record(record, ocr_text, cache_dir=cache_dir)


# ---------------------------------------------------------------------------
# Test 1: Patent → "Grant of:" prefix
# ---------------------------------------------------------------------------

def test_llm_extract_patent_conveyance_prefix():
    record = _record(document_type="Patent")
    result = _call_extract(record)

    assert result.error is None
    assert result.conveyance.value is not None
    assert result.conveyance.value.startswith("Grant of:")
    assert result.conveyance.confidence >= 0.85
    assert result.prompt_tokens == 150
    assert result.completion_tokens == 80


# ---------------------------------------------------------------------------
# Test 2: OGL → Primary Term / Royalty in comments
# ---------------------------------------------------------------------------

def test_llm_extract_ogl_comments_primary_term_and_royalty():
    record = _record(document_type="Oil and Gas Lease")
    ogl_response = _mock_response(
        conveyance_value=(
            "Lease covering:\n\nSection 15,\nTownship 4S, Range 64W,\n"
            "6th P.M., Arapahoe County, Colorado\nContaining approximately 160 acres"
        ),
        comments_value="Primary Term: 5 years\nRoyalty: 1/8\nACTIVE",
        confidence=0.92,
    )
    result = _call_extract(record, mock_return=ogl_response)

    assert result.error is None
    assert "Primary Term" in result.comments.value
    assert "Royalty" in result.comments.value
    assert result.conveyance.value.startswith("Lease covering:")


# ---------------------------------------------------------------------------
# Test 3: Low confidence < 0.60 → field left blank + QA WARNING code
# ---------------------------------------------------------------------------

def test_llm_low_confidence_leaves_field_blank_and_emits_qa_code():
    record = _record(document_type="Mineral Deed")
    low_conf_response = _mock_response(
        conveyance_value="ARTI to:\n\nSection 15, Township 4S, Range 64W",
        comments_value="Excepting coal",
        confidence=0.45,  # below LOW_CONFIDENCE_THRESHOLD = 0.60
    )
    result = _call_extract(record, mock_return=low_conf_response)
    qa_codes = apply_llm_extraction_to_record(record, result)

    # Both fields below threshold — not written
    assert record.conveyance is None
    assert record.comments is None
    assert record.llm_conveyance_confidence is None
    assert "LLM_EXTRACTION_LOW_CONFIDENCE" in qa_codes
    assert "conveyance" in record.source_trace.get("llm_low_confidence_fields", [])


# ---------------------------------------------------------------------------
# Test 4: Missing API key → LLMConfigError (clean error, no crash)
# ---------------------------------------------------------------------------

def test_llm_api_key_missing_raises_config_error():
    record = _record()
    with patch.dict(os.environ, {}, clear=True):
        os.environ.pop("ANTHROPIC_API_KEY", None)
        with pytest.raises(LLMConfigError, match="ANTHROPIC_API_KEY"):
            extract_fields_for_record(record, "some text")


# ---------------------------------------------------------------------------
# Test 5: Cross-reference detection appends *See line
# ---------------------------------------------------------------------------

def test_cross_reference_detection_appends_see_line(tmp_path):
    from src.pipeline import _run_cross_reference_detection

    deed = SourceDocument(
        source_document_id="DOC-000001",
        source_row_number=1,
        document_type="Warranty Deed",
        instrument_number="12345",
        status=ClassificationStatus.INCLUDE_FULL,
    )
    lease = SourceDocument(
        source_document_id="DOC-000002",
        source_row_number=2,
        document_type="Oil and Gas Lease",
        instrument_number="67890",
        book="100",
        page="200",
        status=ClassificationStatus.INCLUDE_FULL,
    )
    # OCR text for deed mentions the lease by book/page
    text_path = tmp_path / "DOC-000001.txt"
    text_path.write_text("This deed is subject to the lease recorded at Book 100, Page 200.", encoding="utf-8")
    deed.extracted_text_path = str(text_path)

    n = _run_cross_reference_detection([deed, lease])

    assert n > 0
    assert deed.comments is not None
    assert "*See" in deed.comments
    assert "Oil and Gas Lease" in deed.comments


# ---------------------------------------------------------------------------
# Test 6: Cache prevents second API call
# ---------------------------------------------------------------------------

def test_llm_cache_prevents_second_api_call(tmp_path):
    record = _record()

    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-sk"}):
        with patch("anthropic.Anthropic") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create.return_value = _mock_response(
                "Grant of:\n\nSection 15, Township 4S, Range 64W", ""
            )

            # First call — hits API
            r1 = extract_fields_for_record(record, "text", cache_dir=tmp_path)
            assert mock_client.messages.create.call_count == 1

            # Second call — should load from cache, not call API again
            r2 = extract_fields_for_record(record, "text", cache_dir=tmp_path)
            assert mock_client.messages.create.call_count == 1  # unchanged

    assert r1.conveyance.value == r2.conveyance.value


# ---------------------------------------------------------------------------
# Test 7: REDLINE records are skipped by run_llm_extraction
# ---------------------------------------------------------------------------

def test_redline_records_skipped_by_run_llm_extraction(tmp_path):
    from src.pipeline import run_llm_extraction

    redline = SourceDocument(
        source_document_id="DOC-000001",
        source_row_number=1,
        document_type="Easement",
        status=ClassificationStatus.REDLINE,
        redline_reason="Non-title instrument.",
        pdf_extraction_status="TEXT_EXTRACTED",
    )
    text_path = tmp_path / "DOC-000001.txt"
    text_path.write_text("Easement text here.", encoding="utf-8")
    redline.extracted_text_path = str(text_path)

    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-sk"}):
        with patch("anthropic.Anthropic") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client

            metrics = run_llm_extraction([redline], output_dir=tmp_path)

    assert metrics["total_eligible"] == 0
    mock_client.messages.create.assert_not_called()


# ---------------------------------------------------------------------------
# Test 8: REVIEW/status text never appears in comments written to record
# ---------------------------------------------------------------------------

def test_llm_comments_never_contains_review_status():
    record = _record(document_type="Correction Deed")
    bad_response = _mock_response(
        conveyance_value="Correction of:\n\nSection 15, Township 4S, Range 64W",
        comments_value="Filed to correct the grantor name.",
        confidence=0.90,
    )
    result = _call_extract(record, mock_return=bad_response)
    apply_llm_extraction_to_record(record, result)

    comments = record.comments or ""
    assert "REVIEW" not in comments
    assert "REVIEW REQUIRED" not in comments
    assert "review_question" not in comments.lower()


# ---------------------------------------------------------------------------
# Test 9: grantor_exact high confidence → overwrites index value
# ---------------------------------------------------------------------------

def test_grantor_exact_high_confidence_overwrites_index():
    record = _record(
        document_type="Mineral Deed",
        grantor="CAVANAUGH PAULINE T",
        grantee="SMITH JOHN",
    )
    mock_resp = _mock_response_with_parties(
        grantor_exact_value="PAULINE T. CAVANAUGH AND THERESIA CAVANAUGH, AS JOINT TENANTS",
        grantee_exact_value="John Smith",
        confidence=0.92,
    )
    result = _call_extract(record, mock_return=mock_resp)
    apply_llm_extraction_to_record(record, result)

    assert record.grantor == "PAULINE T. CAVANAUGH AND THERESIA CAVANAUGH, AS JOINT TENANTS"
    assert record.source_trace.get("grantor_index") == "CAVANAUGH PAULINE T"
    assert record.grantee == "John Smith"
    assert record.source_trace.get("grantee_index") == "SMITH JOHN"


# ---------------------------------------------------------------------------
# Test 10: grantor_exact low confidence → keeps original index value
# ---------------------------------------------------------------------------

def test_grantor_exact_low_confidence_keeps_index():
    record = _record(
        document_type="Mineral Deed",
        grantor="SMITH JOHN",
        grantee="DOE JANE",
    )
    mock_resp = _mock_response_with_parties(
        grantor_exact_value="John Smith (unclear handwriting)",
        grantee_exact_value="Jane Doe",
        confidence=0.70,
    )
    result = _call_extract(record, mock_return=mock_resp)
    apply_llm_extraction_to_record(record, result)

    # Confidence 0.70 < HIGH_CONFIDENCE (0.85) → index value preserved
    assert record.grantor == "SMITH JOHN"
    assert "grantor_index" not in record.source_trace


# ---------------------------------------------------------------------------
# Test 11: instrument_effect ASSIGNS_OGL → reclassified to INCLUDE_FULL
# ---------------------------------------------------------------------------

def test_instrument_effect_assigns_ogl_promotes_to_include():
    record = _record(
        document_type="Assignment",
        status=ClassificationStatus.REVIEW,
    )
    record.classification_reason = "Matched review rule: unclear_assignment"
    record.review_question = "Review whether keyword 'assignment' affects title."

    result = LLMExtractionResult(
        source_document_id=record.source_document_id,
        instrument_effect=LLMFieldResult(
            value="ASSIGNS_OGL", confidence=0.92, provenance="granting clause"
        ),
    )
    tag = apply_instrument_effect_reclassification(record, result)

    assert tag == "include"
    assert record.status == ClassificationStatus.INCLUDE_FULL
    assert record.source_trace.get("reclassified_by") == "llm_instrument_effect"
    assert record.source_trace.get("instrument_effect") == "ASSIGNS_OGL"
    assert record.review_question is None


# ---------------------------------------------------------------------------
# Test 12: instrument_effect EASEMENT_ONLY → reclassified to REDLINE
# ---------------------------------------------------------------------------

def test_instrument_effect_easement_only_demotes_to_redline():
    record = _record(
        document_type="Agreement",
        status=ClassificationStatus.REVIEW,
    )
    record.classification_reason = "No deterministic rule matched"
    record.review_question = "Confirm whether this instrument affects title or minerals."

    result = LLMExtractionResult(
        source_document_id=record.source_document_id,
        instrument_effect=LLMFieldResult(
            value="EASEMENT_ONLY", confidence=0.90, provenance="granting clause mentions easement"
        ),
    )
    tag = apply_instrument_effect_reclassification(record, result)

    assert tag == "redline"
    assert record.status == ClassificationStatus.REDLINE
    assert record.redline_reason is not None
    assert "EASEMENT_ONLY" in record.redline_reason
    assert record.source_trace.get("reclassified_by") == "llm_instrument_effect"


# ---------------------------------------------------------------------------
# Test 13: instrument_effect UNCLEAR → record stays REVIEW
# ---------------------------------------------------------------------------

def test_instrument_effect_unclear_leaves_review():
    record = _record(
        document_type="Assignment",
        status=ClassificationStatus.REVIEW,
    )
    record.classification_reason = "Matched review rule: unclear_assignment"

    result = LLMExtractionResult(
        source_document_id=record.source_document_id,
        instrument_effect=LLMFieldResult(value="UNCLEAR", confidence=0.88),
    )
    tag = apply_instrument_effect_reclassification(record, result)

    assert tag is None
    assert record.status == ClassificationStatus.REVIEW
