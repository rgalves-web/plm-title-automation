"""Permanent DDR QA gates (Collin item 5)."""
from __future__ import annotations

from fractions import Fraction

import openpyxl

from src.dd.dd_qa_gates import (
    mineral_interest_sums_to_one,
    no_commentary_in_client_cells,
    no_template_sample_data,
    seller_wi_matches_expected,
)
from src.dd.title_opinion_parser import TOPartyInterest, TOTract, TitleOpinionExtraction
from src.llm_extractor import LLMFieldResult


def _tract(fractions: list[str]) -> TOTract:
    return TOTract(
        tract_legal_description=LLMFieldResult(value="tract", confidence=1.0),
        mineral_owners=[TOPartyInterest(party=f"O{i}", fraction_text=f, confidence=1.0)
                        for i, f in enumerate(fractions)],
    )


def _ext(tract: TOTract) -> TitleOpinionExtraction:
    return TitleOpinionExtraction(file_number="TO1", tracts=[tract])


def test_mi_sums_to_one_passes_when_exact():
    ext = _ext(_tract(["1/2", "1/4", "1/4"]))
    r = mineral_interest_sums_to_one({"TO1": ext})
    assert r.passed
    assert not r.locations


def test_mi_sums_to_one_fails_and_reports_residual():
    ext = _ext(_tract(["1/2", "1/4"]))  # sums to 3/4
    r = mineral_interest_sums_to_one({"TO1": ext})
    assert not r.passed
    assert r.locations and "residual" in r.locations[0]


def test_seller_wi_gate_matches():
    r = seller_wi_matches_expected(Fraction("0.816596"), "0.816596")
    assert r.passed


def test_seller_wi_gate_mismatch_reports_location():
    r = seller_wi_matches_expected(Fraction("0.625"), "0.816596")
    assert not r.passed
    assert r.locations and "Ownership Report" in r.locations[0]


def test_seller_wi_gate_skipped_when_unconfigured():
    assert seller_wi_matches_expected(Fraction("0.5"), None).passed


def _wb_with(sheet: str, cell: str, value: str):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet
    ws[cell] = value
    return wb


def test_no_commentary_gate_flags_triage_text():
    wb = _wb_with("Lease Review", "C3", "REVIEW REQUIRED — needs manual check")
    r = no_commentary_in_client_cells(wb)
    assert not r.passed
    assert "Lease Review · C3" in r.locations[0]


def test_no_template_data_gate_flags_placeholder():
    wb = _wb_with("Runsheet", "A2", "636.13 acres in Reeves County")
    r = no_template_sample_data(wb)
    assert not r.passed


def test_gates_ignore_audit_trail_sheet():
    wb = openpyxl.Workbook()
    wb.active.title = "DD_Audit_Trail"
    wb.active["A1"] = "REVIEW REQUIRED note in the provenance layer"
    assert no_commentary_in_client_cells(wb).passed
