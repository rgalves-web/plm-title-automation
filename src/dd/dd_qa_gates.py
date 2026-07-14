"""Permanent QA gates for the DDR (Collin item 5).

Each gate returns a GateResult with a pass/fail and, on failure, a SPECIFIC,
actionable location (tab, cell/row, what to check, which source to consult).
Failing gates block the pipeline's "done" status — they never silently pass.

Gates:
  A. mineral_interest_sums_to_one  — MI per controlling tract sums to 1/1.
  B. seller_wi_matches_expected    — aggregate leasehold WI == manifest.expected_seller_wi.
  C. no_commentary_in_client_cells — no triage/commentary text in a client tab.
  D. no_template_sample_data       — no leftover template placeholder text.

All fraction arithmetic is exact (fractions.Fraction); nothing is estimated.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any

from src.dd.unit_aggregation import parse_fraction_text

# Tolerance for the exact-fraction comparisons (values should be exact; this
# only absorbs an 8-decimal display rounding when a source printed a decimal).
_TOL = Fraction(1, 10**6)

# Commentary/triage strings that must never reach a client-facing cell.
_TRIAGE_MARKERS = ("REVIEW REQUIRED", "REDLINE", "DUPLICATE OF", "NEEDS REVIEW",
                   "PARSE ERROR", "TODO", "FIXME", "NOT PROVIDED IN OCR")
# Template placeholder families (mirror ddr_writer.PLACEHOLDER_MARKERS).
_PLACEHOLDER_MARKERS = ("***", "Reeves", "636.13", "3-11", "A.E. Carroll", "Forest Oil")
_AUDIT_SHEET = "DD_Audit_Trail"


@dataclass
class GateResult:
    name: str
    passed: bool
    detail: str
    locations: list[str] = field(default_factory=list)  # specific tab·cell·what-to-check

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail,
                "locations": self.locations}


def mineral_interest_sums_to_one(controlling: dict[str, Any]) -> GateResult:
    """MI per controlling tract must sum to 1/1 (100% of the tract's minerals
    accounted for). controlling maps file_number -> TitleOpinionExtraction."""
    locations: list[str] = []
    all_ok = True
    for file_number, extraction in controlling.items():
        for i, tract in enumerate(getattr(extraction, "tracts", []) or []):
            owners = getattr(tract, "mineral_owners", []) or []
            if not owners:
                continue
            total = Fraction(0)
            unparsed = 0
            for owner in owners:
                frac = parse_fraction_text(owner.fraction_text)
                if frac is None:
                    unparsed += 1
                else:
                    total += frac
            residual = Fraction(1) - total
            if abs(residual) > _TOL or unparsed:
                all_ok = False
                locations.append(
                    f"{file_number} · tract {i + 1} · MINERALS section: mineral interest sums to "
                    f"{float(total):.8f} (residual {float(residual):+.8f}"
                    + (f"; {unparsed} owner fraction(s) unparsed" if unparsed else "")
                    + ") — reconcile the mineral ownership against the title opinion.")
    return GateResult(
        "mineral_interest_sums_to_one", all_ok,
        "MI sums to 1/1 for every controlling tract." if all_ok
        else "One or more tracts do not sum to 1/1 minerals.",
        locations)


def seller_wi_matches_expected(computed_wi: Fraction | None, expected_wi: str | None) -> GateResult:
    """Aggregate leasehold WI must equal the expected value from
    manifest/config. Skipped (passing) when no expected value is configured."""
    if expected_wi is None:
        return GateResult("seller_wi_matches_expected", True,
                          "No expected Seller WI configured — gate skipped.")
    if computed_wi is None:
        return GateResult("seller_wi_matches_expected", False,
                          "Seller WI was not computed but an expected value is configured.",
                          [f"Ownership Report · row 5 (Seller WI) · expected {expected_wi}, got none — "
                           "verify the controlling opinions parsed."])
    expected = parse_fraction_text(str(expected_wi))
    if expected is None:
        return GateResult("seller_wi_matches_expected", False,
                          f"Configured expected Seller WI is not a parseable value: {expected_wi!r}")
    ok = abs(computed_wi - expected) <= _TOL
    return GateResult(
        "seller_wi_matches_expected", ok,
        f"Computed Seller WI {float(computed_wi):.6f} "
        + ("matches" if ok else "does NOT match")
        + f" expected {float(expected):.6f}.",
        [] if ok else
        [f"Ownership Report · row 5 (Seller WI) · computed {float(computed_wi):.6f} vs expected "
         f"{float(expected):.6f} — reconcile per-tract WI against the controlling opinions."])


def _scan_workbook(workbook, markers, gate_name: str, what: str) -> GateResult:
    locations: list[str] = []
    for sheet_name in workbook.sheetnames:
        if sheet_name == _AUDIT_SHEET:  # provenance layer is not client-facing
            continue
        ws = workbook[sheet_name]
        for row in ws.iter_rows():
            for cell in row:
                value = cell.value
                if isinstance(value, str):
                    hit = next((m for m in markers if (m in value) or (m.upper() in value.upper())), None)
                    if hit:
                        locations.append(f"{sheet_name} · {cell.coordinate} · contains {hit!r}: "
                                         f"{value[:60]!r}")
    ok = not locations
    return GateResult(gate_name, ok, f"No {what} in client-facing cells." if ok
                      else f"{len(locations)} client-facing cell(s) contain {what}.", locations)


def no_commentary_in_client_cells(workbook) -> GateResult:
    return _scan_workbook(workbook, _TRIAGE_MARKERS, "no_commentary_in_client_cells",
                          "commentary / triage text")


def no_template_sample_data(workbook) -> GateResult:
    return _scan_workbook(workbook, _PLACEHOLDER_MARKERS, "no_template_sample_data",
                          "template / sample data")


def run_workbook_gates(workbook) -> list[GateResult]:
    return [no_commentary_in_client_cells(workbook), no_template_sample_data(workbook)]
