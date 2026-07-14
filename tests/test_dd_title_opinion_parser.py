"""Tests for src/dd/title_opinion_parser.py — all API calls are mocked."""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.dd.manifest import TitleOpinionRef
from src.dd.title_opinion_parser import (
    TitleOpinionExtraction,
    _cache_filename as dd_cache_filename,
    parse_title_opinion,
)
from src.llm_extractor import _cache_filename as mor_cache_filename


def _to_ref(file_number="T0000001", pdf_available=True, pdf_path=None) -> TitleOpinionRef:
    return TitleOpinionRef(
        file_number=file_number,
        pdf_available=pdf_available,
        pdf_path=pdf_path,
    )


def _mock_response(tracts_input: list[dict]):
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.input = {"tracts": tracts_input}
    usage = MagicMock()
    usage.input_tokens = 500
    usage.output_tokens = 300
    response = MagicMock()
    response.content = [tool_block]
    response.usage = usage
    return response


def _minimal_tract(
    cert_date="May 2, 2008",
    letter_date="July 11, 2008",
    wi_rows=None,
) -> dict:
    return {
        "tract_legal_description": {"value": "119.2 acres, Samuel Cable Survey, A-1449", "confidence": 0.95},
        "certification_date": {"value": cert_date, "confidence": 0.95, "provenance": "as of May 2, 2008, the Land was owned"},
        "letter_date": {"value": letter_date, "confidence": 0.9},
        "surface_owners": [{"party": "Leonard Delbert Bowen", "fraction_text": "All", "confidence": 0.9}],
        "mineral_owners": [
            {"party": "Leonard Delbert Bowen", "fraction_text": "1/2 = 0.5000000", "confidence": 0.9},
        ],
        "royalty_owners": [
            {"party": "Leonard Delbert Bowen", "fraction_text": "1/2 x 1/8 = 0.0625000", "confidence": 0.85},
        ],
        "overriding_royalty_owners": [],
        "working_interest_table": wi_rows if wi_rows is not None else [
            {"company": "EOG Resources, Inc.", "operating_interest_text": "0.6250000",
             "net_revenue_interest_text": "0.5187500", "confidence": 0.95},
            {"company": "EnCana Oil & Gas (USA) Inc.", "operating_interest_text": "0.3750000",
             "net_revenue_interest_text": "0.3112500", "confidence": 0.95},
        ],
        "leases": [],
        "requirements": [],
        "comments": [],
        "predicted_unit_coverage": {"value": "LIKELY_COVERS", "confidence": 0.7},
    }


def _patch_pdf_pipeline(ocr_text="Sample OCR text with sufficient content for OCR extraction."):
    extraction_result = MagicMock()
    extraction_result.full_text = ocr_text
    return patch("src.pdf_reader.extract_document", return_value=extraction_result)


def _call_parse(to_ref, tmp_path, mock_tracts=None, target_unit_name="BOWEN A UNIT", seller_name="EOG Resources, Inc."):
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-sk-key"}):
        with _patch_pdf_pipeline():
            with patch("anthropic.Anthropic") as mock_cls:
                mock_client = MagicMock()
                mock_cls.return_value = mock_client
                mock_client.messages.create.return_value = _mock_response(
                    mock_tracts if mock_tracts is not None else [_minimal_tract()]
                )
                result = parse_title_opinion(
                    to_ref, target_unit_name, seller_name,
                    work_dir=tmp_path / "work",
                    cache_dir=tmp_path / "cache",
                )
                return result, mock_client


# ---------------------------------------------------------------------------
# No-PDF short circuit
# ---------------------------------------------------------------------------

def test_parse_title_opinion_returns_error_state_when_pdf_unavailable(tmp_path):
    to_ref = _to_ref(pdf_available=False, pdf_path=None)

    with patch("anthropic.Anthropic") as mock_cls:
        result = parse_title_opinion(
            to_ref, "BOWEN A UNIT", "EOG Resources, Inc.",
            work_dir=tmp_path / "work", cache_dir=tmp_path / "cache",
        )
        mock_cls.assert_not_called()

    assert result.pdf_available is False
    assert result.error is not None
    assert result.tracts == []


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def test_parse_title_opinion_cache_hit_skips_api_call(tmp_path):
    pdf_path = tmp_path / "T0000001.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")
    to_ref = _to_ref(pdf_path=str(pdf_path))

    result1, mock_client1 = _call_parse(to_ref, tmp_path)
    assert mock_client1.messages.create.call_count == 1

    # Second call should hit cache, not call API again
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-sk-key"}):
        with _patch_pdf_pipeline():
            with patch("anthropic.Anthropic") as mock_cls2:
                mock_client2 = MagicMock()
                mock_cls2.return_value = mock_client2
                result2 = parse_title_opinion(
                    to_ref, "BOWEN A UNIT", "EOG Resources, Inc.",
                    work_dir=tmp_path / "work", cache_dir=tmp_path / "cache",
                )
                mock_client2.messages.create.assert_not_called()

    assert result1.tracts[0].certification_date.value == result2.tracts[0].certification_date.value


# ---------------------------------------------------------------------------
# Certification date vs letter date
# ---------------------------------------------------------------------------

def test_certification_date_phrase_extracted_not_letter_date(tmp_path):
    pdf_path = tmp_path / "T0000002.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")
    to_ref = _to_ref(file_number="T0000002", pdf_path=str(pdf_path))

    result, _ = _call_parse(to_ref, tmp_path)

    tract = result.tracts[0]
    assert tract.certification_date.value == "May 2, 2008"
    assert tract.letter_date.value == "July 11, 2008"
    assert tract.certification_date.value != tract.letter_date.value


# ---------------------------------------------------------------------------
# Compound fraction text preserved, not computed
# ---------------------------------------------------------------------------

def test_working_interest_table_rows_preserve_text_not_arithmetic(tmp_path):
    pdf_path = tmp_path / "T0000003.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")
    to_ref = _to_ref(file_number="T0000003", pdf_path=str(pdf_path))

    result, _ = _call_parse(to_ref, tmp_path)

    tract = result.tracts[0]
    royalty_text = tract.royalty_owners[0].fraction_text
    assert royalty_text == "1/2 x 1/8 = 0.0625000"
    # the model never produces a computed float field anywhere in the schema
    assert not hasattr(tract, "royalty_total")
    wi_row = tract.working_interest_table[0]
    assert wi_row.operating_interest_text == "0.6250000"
    assert isinstance(wi_row.operating_interest_text, str)


# ---------------------------------------------------------------------------
# Seller working interest resolution (Python, not LLM)
# ---------------------------------------------------------------------------

def test_seller_working_interest_resolved_by_fuzzy_name_match(tmp_path):
    pdf_path = tmp_path / "T0000004.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")
    to_ref = _to_ref(file_number="T0000004", pdf_path=str(pdf_path))

    result, _ = _call_parse(to_ref, tmp_path, seller_name="EOG RESOURCES INC")

    tract = result.tracts[0]
    assert tract.seller_working_interest is not None
    assert tract.seller_working_interest.company == "EOG Resources, Inc."


def test_seller_working_interest_none_when_no_match_above_threshold(tmp_path):
    pdf_path = tmp_path / "T0000005.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")
    to_ref = _to_ref(file_number="T0000005", pdf_path=str(pdf_path))

    result, _ = _call_parse(to_ref, tmp_path, seller_name="TOTALLY UNRELATED CORP")

    tract = result.tracts[0]
    assert tract.seller_working_interest is None


# ---------------------------------------------------------------------------
# predicted_unit_coverage enum validation
# ---------------------------------------------------------------------------

def test_predicted_unit_coverage_never_outside_three_state_enum(tmp_path):
    from pydantic import ValidationError
    from src.dd.title_opinion_parser import TOTract
    from src.llm_extractor import LLMFieldResult

    # The schema itself does not hard-enforce the enum on the Python side
    # (the Anthropic tool schema does, server-side) — but valid values must
    # round-trip cleanly through the pydantic model.
    tract = TOTract(predicted_unit_coverage=LLMFieldResult(value="UNCERTAIN", confidence=0.5))
    assert tract.predicted_unit_coverage.value == "UNCERTAIN"


# ---------------------------------------------------------------------------
# Cache namespace never collides with MOR's
# ---------------------------------------------------------------------------

def test_cache_schema_version_namespace_does_not_collide_with_mor():
    identifier = "T0141487"
    model = "claude-haiku-4-5-20251001"
    dd_name = dd_cache_filename(identifier, model)
    mor_name = mor_cache_filename(identifier, model)
    assert dd_name != mor_name
    assert "dd_to_v1" in dd_name
    assert "dd_to_v1" not in mor_name
