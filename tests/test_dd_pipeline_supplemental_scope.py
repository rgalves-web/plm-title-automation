"""Tests for src/dd/dd_pipeline.py's supplemental scope filter and
controlling-certification-date resolution — the deterministic Step 2 of the
PLM landman instructions ("run supplemental title from the certification
date of the title opinion to present day, limited to the interest of the
Seller"). Also guards that adding ProjectType to ProjectMetadata never
changes MOR's default behavior.
"""
from __future__ import annotations

from datetime import date

import pytest

from src.dd.dd_pipeline import (
    DD_NO_CONTROLLING_CERTIFICATION_DATE,
    OUTSIDE_SELLER_INTEREST_REASON,
    PREDATES_CERTIFICATION_REASON,
    SupplementalScopeError,
    apply_supplemental_scope_filter,
    controlling_certification_date_qa_exception,
    resolve_controlling_certification_date,
)
from src.dd.manifest import TitleOpinionRef, UnitManifest
from src.dd.title_opinion_parser import TOTract, TitleOpinionExtraction
from src.llm_extractor import LLMFieldResult
from src.schemas import ClassificationStatus, ProjectMetadata, ProjectType, SourceDocument


def _to_extraction(file_number: str, cert_date_text: str | None, error: str | None = None) -> TitleOpinionExtraction:
    if error:
        return TitleOpinionExtraction(file_number=file_number, error=error)
    return TitleOpinionExtraction(
        file_number=file_number,
        tracts=[TOTract(certification_date=LLMFieldResult(value=cert_date_text, confidence=0.9))],
    )


def _manifest(title_opinions: list[TitleOpinionRef]) -> UnitManifest:
    return UnitManifest(unit_name="BOWEN A UNIT", title_opinions=title_opinions)


# ---------------------------------------------------------------------------
# resolve_controlling_certification_date
# ---------------------------------------------------------------------------

def test_controlling_date_is_latest_among_confirmed_tos():
    manifest = _manifest(
        [
            TitleOpinionRef(file_number="T1", confirm_coverage=True),
            TitleOpinionRef(file_number="T2", confirm_coverage=True),
        ]
    )
    extractions = {
        "T1": _to_extraction("T1", "May 2, 2008"),
        "T2": _to_extraction("T2", "January 10, 2015"),
    }
    result = resolve_controlling_certification_date(manifest, extractions)
    assert result == date(2015, 1, 10)


def test_controlling_date_ignores_unconfirmed_tos():
    manifest = _manifest(
        [
            TitleOpinionRef(file_number="T1", confirm_coverage=True),
            TitleOpinionRef(file_number="T2", confirm_coverage=False),
        ]
    )
    extractions = {
        "T1": _to_extraction("T1", "May 2, 2008"),
        "T2": _to_extraction("T2", "January 10, 2099"),  # later, but not confirmed — must be ignored
    }
    result = resolve_controlling_certification_date(manifest, extractions)
    assert result == date(2008, 5, 2)


def test_controlling_date_ignores_errored_or_missing_extractions():
    manifest = _manifest(
        [
            TitleOpinionRef(file_number="T1", confirm_coverage=True),
            TitleOpinionRef(file_number="T2", confirm_coverage=True),
            TitleOpinionRef(file_number="T3", confirm_coverage=True),
        ]
    )
    extractions = {
        "T1": _to_extraction("T1", "May 2, 2008"),
        "T2": _to_extraction("T2", None, error="OCR failed"),
        # T3 missing entirely (e.g. no PDF available, never parsed)
    }
    result = resolve_controlling_certification_date(manifest, extractions)
    assert result == date(2008, 5, 2)


def test_controlling_date_raises_when_none_resolvable():
    manifest = _manifest([TitleOpinionRef(file_number="T1", confirm_coverage=True, pdf_available=False)])
    with pytest.raises(SupplementalScopeError):
        resolve_controlling_certification_date(manifest, {})


def test_controlling_date_error_produces_hard_stop_qa_exception():
    manifest = _manifest([TitleOpinionRef(file_number="T1", confirm_coverage=True)])
    try:
        resolve_controlling_certification_date(manifest, {})
    except SupplementalScopeError as exc:
        qa_exception = controlling_certification_date_qa_exception(manifest, exc)
    assert qa_exception.severity == "ERROR"
    assert qa_exception.code == DD_NO_CONTROLLING_CERTIFICATION_DATE


# ---------------------------------------------------------------------------
# apply_supplemental_scope_filter
# ---------------------------------------------------------------------------

def _record(**overrides) -> SourceDocument:
    defaults = dict(
        source_document_id="DOC-1",
        source_row_number=1,
        document_type="Assignment",
        grantor="EOG Resources, Inc.",
        grantee="Third Party LLC",
        recording_date=date(2020, 1, 1),
        status=ClassificationStatus.INCLUDE_FULL,
    )
    defaults.update(overrides)
    return SourceDocument(**defaults)


def test_record_after_certification_date_and_touching_seller_stays_included():
    record = _record(recording_date=date(2020, 1, 1), grantor="EOG Resources, Inc.")
    apply_supplemental_scope_filter([record], date(2008, 5, 2), "EOG RESOURCES INC")
    assert record.status == ClassificationStatus.INCLUDE_FULL
    assert record.redline_reason is None


def test_record_before_certification_date_is_redlined():
    record = _record(recording_date=date(2005, 1, 1))
    apply_supplemental_scope_filter([record], date(2008, 5, 2), "EOG RESOURCES INC")
    assert record.status == ClassificationStatus.REDLINE
    assert record.redline_reason == PREDATES_CERTIFICATION_REASON


def test_record_on_certification_date_exactly_is_redlined_not_strictly_after():
    record = _record(recording_date=date(2008, 5, 2))
    apply_supplemental_scope_filter([record], date(2008, 5, 2), "EOG RESOURCES INC")
    assert record.status == ClassificationStatus.REDLINE
    assert record.redline_reason == PREDATES_CERTIFICATION_REASON


def test_record_not_touching_seller_interest_is_redlined():
    record = _record(
        recording_date=date(2020, 1, 1),
        grantor="Totally Unrelated Corp",
        grantee="Another Unrelated Corp",
    )
    apply_supplemental_scope_filter([record], date(2008, 5, 2), "EOG RESOURCES INC")
    assert record.status == ClassificationStatus.REDLINE
    assert record.redline_reason == OUTSIDE_SELLER_INTEREST_REASON


def test_seller_interest_match_is_fuzzy_tolerant_of_punctuation():
    # "EOG Resources, Inc." (PDF-style) vs "EOG RESOURCES INC" (manifest seller_name)
    record = _record(recording_date=date(2020, 1, 1), grantee="EOG Resources, Inc.", grantor="Third Party LLC")
    apply_supplemental_scope_filter([record], date(2008, 5, 2), "EOG RESOURCES INC")
    assert record.status == ClassificationStatus.INCLUDE_FULL


def test_certification_date_written_to_typed_field_and_source_trace_for_in_and_out_of_scope():
    in_scope = _record(source_document_id="DOC-IN", recording_date=date(2020, 1, 1))
    out_of_scope = _record(source_document_id="DOC-OUT", recording_date=date(2005, 1, 1))
    apply_supplemental_scope_filter([in_scope, out_of_scope], date(2008, 5, 2), "EOG RESOURCES INC")

    for record in (in_scope, out_of_scope):
        assert record.certification_date == date(2008, 5, 2)
        assert record.source_trace["certification_date"] == "2008-05-02"


def test_already_redlined_records_are_not_relabeled():
    record = _record(status=ClassificationStatus.REDLINE, redline_reason="Pre-existing reason")
    apply_supplemental_scope_filter([record], date(2008, 5, 2), "EOG RESOURCES INC")
    assert record.redline_reason == "Pre-existing reason"


def test_missing_seller_name_skips_seller_filter_but_keeps_date_filter():
    record = _record(recording_date=date(2020, 1, 1), grantor="Anyone", grantee="Anyone Else")
    apply_supplemental_scope_filter([record], date(2008, 5, 2), None)
    assert record.status == ClassificationStatus.INCLUDE_FULL


# ---------------------------------------------------------------------------
# MOR regression guard — adding ProjectType must never change MOR's defaults
# ---------------------------------------------------------------------------

def test_mor_default_unaffected_by_project_type_field():
    metadata = ProjectMetadata(project_name="Arapahoe", county="Arapahoe", state="Colorado")
    assert metadata.project_type == ProjectType.MOR
    assert metadata.unit_name is None

    record = SourceDocument(
        source_document_id="DOC-000001",
        source_row_number=2,
        document_type="Patent",
        status=ClassificationStatus.INCLUDE_FULL,
    )
    assert record.certification_date is None


# ---------------------------------------------------------------------------
# resolve_seller_wi — WORKING interest must never be a swapped NRI value.
# ---------------------------------------------------------------------------

from fractions import Fraction

from src.dd.dd_pipeline import resolve_seller_wi
from src.dd.title_opinion_parser import TOPartyInterest, TOWorkingInterestRow


def _tract_with_seller(oi_text, nri_text, *, minerals="1", royalty="1/8", acres="100 acres"):
    return TOTract(
        tract_legal_description=LLMFieldResult(value=f"{acres} out of the Survey", confidence=1.0),
        certification_date=LLMFieldResult(value="June 18, 2009", confidence=1.0),
        mineral_owners=[TOPartyInterest(party="Owner", fraction_text=minerals, confidence=1.0)],
        royalty_owners=[TOPartyInterest(party="Owner", fraction_text=royalty, confidence=1.0)],
        working_interest_table=[
            TOWorkingInterestRow(company="EOG", operating_interest_text=oi_text,
                                 net_revenue_interest_text=nri_text, confidence=1.0)
        ],
        seller_working_interest=TOWorkingInterestRow(
            company="EOG", operating_interest_text=oi_text,
            net_revenue_interest_text=nri_text, confidence=1.0),
    )


def test_resolve_seller_wi_uses_working_column_when_gt_nri():
    tract = _tract_with_seller("1.00000000", ".76250000")
    wi, needs_review = resolve_seller_wi(tract)
    assert wi == Fraction(1)
    assert needs_review is False


def test_resolve_seller_wi_recovers_working_from_swapped_nri_formula():
    # Cox bug: OI field holds the NRI calculation formula, NRI field holds the
    # net revenue decimal. WI must be recovered as .84953704, flagged for review.
    tract = _tract_with_seller(
        "[(49.768518% x 4/5) plus (35.185186% x 75%)]", ".66203704"
    )
    wi, needs_review = resolve_seller_wi(tract)
    assert wi == Fraction("0.49768518") + Fraction("0.35185186")
    assert abs(float(wi) - 0.84953704) < 1e-8
    assert needs_review is True


def test_resolve_seller_wi_flags_when_unrecoverable():
    tract = _tract_with_seller("garbled text", "also garbled")
    wi, needs_review = resolve_seller_wi(tract)
    assert wi is None
    assert needs_review is True
