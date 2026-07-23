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
            unparsed_entries: list[str] = []
            for owner in owners:
                frac = parse_fraction_text(owner.fraction_text)
                if frac is None:
                    unparsed_entries.append(f"{owner.party!r} = {owner.fraction_text!r} [UNPARSED]")
                else:
                    total += frac
            residual = Fraction(1) - total
            if abs(residual) > _TOL or unparsed_entries:
                all_ok = False
                locations.append(
                    f"{file_number} · tract {i + 1} · MINERALS section: {len(owners)} owner(s), "
                    f"parsed sum {float(total):.8f}, residual {float(residual):+.8f}"
                    + (f", {len(unparsed_entries)} entry(ies) unparsed" if unparsed_entries else "")
                    + " — reconcile the mineral ownership against the title opinion.")
                # Pinpoint the exact unparsed MINERALS entries for the reviewer.
                for entry in unparsed_entries:
                    locations.append(f"    {file_number} · MINERALS · {entry}")
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


def mineral_interest_within_tract_not_over_one(rows: list[dict[str, Any]]) -> GateResult:
    """Sheet-level sanity gate (Collin item 1 regression guard): the populated
    Mineral Interest (MI) values of the leases drawing from one tract must not
    sum to more than 1/1. A tract's mineral ownership is a partition of unity, so
    a sum > 1 means MI was flattened — e.g. every lease in the tract was written
    with the same owner's fraction (13 × 5/36 = 1.81), which this gate catches
    before the workbook ships. Leases with no MI yet (pending) contribute 0."""
    by_tract: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        key = row.get("tract_key")
        mi = row.get("mi_value")
        if key is None or mi is None:
            continue
        by_tract.setdefault(key, []).append(row)

    locations: list[str] = []
    for key, tract_rows in by_tract.items():
        total = Fraction(0)
        for row in tract_rows:
            frac = row["mi_value"]
            total += frac if isinstance(frac, Fraction) else Fraction(str(frac))
        if total - Fraction(1) > _TOL:
            leases = ", ".join(str(r.get("lease_no") or "?") for r in tract_rows)
            locations.append(
                f"tract {key!r}: {len(tract_rows)} lease(s) with populated MI sum to "
                f"{float(total):.6f} (> 1/1) — MI is flattened/over-counted; each lessor's "
                f"MI must be its OWN mineral-owner fraction. Leases: {leases}")
    ok = not locations
    return GateResult(
        "mineral_interest_within_tract_not_over_one", ok,
        "Populated MI within every tract sums to <= 1/1." if ok
        else f"{len(locations)} tract(s) have populated MI summing to more than 1/1.",
        locations)


def workbook_headline_wi(
    rows: list[dict[str, Any]],
    unit_gross_acres: Fraction | None,
    expected_wi: str | None,
) -> GateResult:
    """Validate the HEADLINE Seller WI the *workbook* itself displays (Collin
    item 2). The Ownership Report's D5 = SUM(net acres)/A5, where each lease's
    net acres = R(tract gross) x S(MI) x T(WI); a row missing any of the three
    contributes zero. openpyxl does not evaluate formulas, so we replicate D5's
    arithmetic here rather than trusting the internal aggregation. If rows are
    still pending MI/acres the headline is UNDERSTATED versus the expected WI —
    the gate fails and names how many rows are pending, so the number the client
    sees is never silently different from the number the pipeline validated."""
    if expected_wi is None or unit_gross_acres in (None, 0):
        return GateResult("workbook_headline_wi", True,
                          "No expected Seller WI / unit gross configured — gate skipped.")
    expected = parse_fraction_text(str(expected_wi))
    if expected is None:
        return GateResult("workbook_headline_wi", False,
                          f"Configured expected Seller WI is not parseable: {expected_wi!r}")

    def _f(v):
        if v is None:
            return None
        return v if isinstance(v, Fraction) else Fraction(str(v))

    net_acres = Fraction(0)
    pending: list[str] = []
    for row in rows:
        r, s, t = _f(row.get("tract_gross_acres")), _f(row.get("mi_value")), _f(row.get("wi_value"))
        if r is None or s is None or t is None:
            missing = [n for n, v in (("tract gross", r), ("MI", s), ("WI", t)) if v is None]
            pending.append(f"{row.get('lease_no') or '?'} (missing {', '.join(missing)})")
            continue
        net_acres += r * s * t
    headline = net_acres / Fraction(str(unit_gross_acres))
    ok = abs(headline - expected) <= _TOL
    detail = (f"Workbook headline Seller WI (Ownership Report D5) = {float(headline):.6f}; "
              f"expected {float(expected):.6f}"
              + (f"; {len(pending)} row(s) still pending MI/acres" if pending else "") + ".")
    locations: list[str] = []
    if not ok:
        locations.append(
            f"Ownership Report · D5 · workbook shows {float(headline):.6f} but pipeline expects "
            f"{float(expected):.6f} — {len(pending)} row(s) pending MI/acres understate the headline; "
            "resolve them or the Summary must state the headline is understated.")
        for p in pending:
            locations.append(f"    pending · {p}")
    return GateResult("workbook_headline_wi", ok, detail, locations)


def every_blank_has_a_reason(
    blanks: list[tuple[str, str, str]],
    registry: Any,
) -> GateResult:
    """No silent blanks (Maxwell lessons item 1): every client-facing cell the
    pipeline is RESPONSIBLE for and left empty must carry a recorded reason in
    the audit layer. A blank with no reason is indistinguishable from work not
    done, so it fails the run rather than shipping.

    blanks: (sheet, location, field_name) the writer owns but did not populate.
    registry: a PendingRegistry holding the recorded reasons.
    """
    missing = [b for b in blanks if not registry.has(*b)]
    locations = [
        f"{sheet} · {location} · {field_name} is blank with no recorded reason — "
        "record a PendingReason (pending_document / awaiting_reviewer_decision / "
        "clause_absent / source_not_title / unresolved_identity / not_found) or populate it."
        for sheet, location, field_name in missing[:40]
    ]
    if len(missing) > 40:
        locations.append(f"    … and {len(missing) - 40} more unexplained blank(s).")
    ok = not missing
    return GateResult(
        "every_blank_has_a_reason", ok,
        f"All {len(blanks)} pipeline-owned blank(s) carry a reason." if ok
        else f"{len(missing)} client-facing blank(s) have no recorded reason.",
        locations)


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
