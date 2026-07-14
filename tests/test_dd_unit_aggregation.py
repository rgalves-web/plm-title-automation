"""Tests for src/dd/unit_aggregation.py — Fraction-exact, no float roundoff."""
from __future__ import annotations

from fractions import Fraction

import pytest

from src.dd.manifest import RepresentedInterest, UnitManifest
from src.dd.unit_aggregation import (
    AggregationError,
    DD_RECONCILIATION_TOLERANCE,
    LeaseTractRow,
    aggregate_unit,
    derive_wi_from_nri_formula,
    parse_fraction_text,
    reconcile,
    reconciliation_qa_exceptions,
    run_dd_aggregation,
)


# ---------------------------------------------------------------------------
# parse_fraction_text
# ---------------------------------------------------------------------------

def test_compound_fraction_text_parsing():
    assert parse_fraction_text("1/2 x 1/8") == Fraction(1, 16)


def test_compound_fraction_text_with_computed_suffix_stripped():
    assert parse_fraction_text("1/2 x 1/8 = 0.0625000") == Fraction(1, 16)


def test_plain_fraction_text_parsing():
    assert parse_fraction_text("1/2") == Fraction(1, 2)


def test_decimal_text_parsing_exact():
    assert parse_fraction_text("0.6250000") == Fraction(5, 8)


def test_all_keyword_parses_to_full_interest():
    assert parse_fraction_text("All") == Fraction(1, 1)
    assert parse_fraction_text("All.") == Fraction(1, 1)


def test_unparseable_text_returns_none():
    assert parse_fraction_text("see attached exhibit") is None
    assert parse_fraction_text("") is None
    assert parse_fraction_text(None) is None


def test_represented_wi_parsed_from_decimal_string_exactly():
    # Fraction("0.78813617") must round-trip exactly — Fraction(float(...)) would not.
    value = parse_fraction_text("0.78813617")
    assert value == Fraction(78813617, 100000000)
    assert float(value) == 0.78813617


# ---------------------------------------------------------------------------
# Per-row formula shape (mirrors the real Ownership Report template example)
# ---------------------------------------------------------------------------

def test_company_net_acres_formula_matches_template_formula_shape():
    row = LeaseTractRow(
        lease_no="L1",
        tract_gross_acres=Fraction("629.53"),
        mi_value=Fraction(7, 1280),
        wi_value=Fraction(1),
        royalty=Fraction("0.25"),
        orri_burdens=Fraction(0),
    )
    expected_net_acres = Fraction("629.53") * Fraction(7, 1280) * Fraction(1)
    assert row.company_net_acres == expected_net_acres
    assert row.nri_value == Fraction("0.75")
    assert row.company_net_revenue_acres == expected_net_acres * Fraction("0.75")


# ---------------------------------------------------------------------------
# Aggregation roll-up
# ---------------------------------------------------------------------------

def test_aggregate_unit_sums_rows_and_divides_by_unit_gross():
    rows = [
        LeaseTractRow("L1", Fraction(100), Fraction(1, 2), Fraction(1), Fraction(1, 8)),
        LeaseTractRow("L2", Fraction(100), Fraction(1, 2), Fraction(1), Fraction(1, 8)),
    ]
    result = aggregate_unit(Fraction(200), rows)

    expected_net_acres = Fraction(50) + Fraction(50)
    assert result.company_net_acres_total == expected_net_acres
    assert result.seller_wi == expected_net_acres / Fraction(200)


def test_aggregate_unit_raises_on_non_positive_gross_acres():
    with pytest.raises(AggregationError):
        aggregate_unit(Fraction(0), [])


# ---------------------------------------------------------------------------
# Reconciliation tolerance — exact boundary
# ---------------------------------------------------------------------------

def _aggregation_with_seller_wi(seller_wi: Fraction):
    rows = [LeaseTractRow("L1", seller_wi, Fraction(1), Fraction(1), Fraction(0))]
    return aggregate_unit(Fraction(1), rows)


def test_reconciliation_pass_within_tolerance():
    aggregation = _aggregation_with_seller_wi(Fraction("0.9975"))
    reconciliation = reconcile(aggregation, represented_wi="0.9975", represented_nri="0.9975")
    assert reconciliation.wi_status == "PASS"
    assert reconciliation_qa_exceptions(reconciliation) == []


def test_reconciliation_warning_exceeds_tolerance():
    represented = Fraction("0.9975")
    computed = represented + DD_RECONCILIATION_TOLERANCE + Fraction(1, 1_000_000)
    aggregation = _aggregation_with_seller_wi(computed)
    reconciliation = reconcile(aggregation, represented_wi=str(represented), represented_nri=str(represented))
    assert reconciliation.wi_status == "WARNING"
    codes = [e.code for e in reconciliation_qa_exceptions(reconciliation)]
    assert "DD_WI_RECONCILIATION" in codes


def test_reconciliation_at_exact_tolerance_boundary_is_pass():
    represented = Fraction("0.9975")
    computed = represented + DD_RECONCILIATION_TOLERANCE  # exactly at tolerance, not exceeding
    aggregation = _aggregation_with_seller_wi(computed)
    reconciliation = reconcile(aggregation, represented_wi=str(represented), represented_nri=str(represented))
    assert reconciliation.wi_status == "PASS"


def test_reconciliation_never_produces_error_severity():
    represented = Fraction("0.5")
    computed = Fraction("0.999")  # huge delta
    aggregation = _aggregation_with_seller_wi(computed)
    reconciliation = reconcile(aggregation, represented_wi=str(represented), represented_nri=str(represented))
    exceptions = reconciliation_qa_exceptions(reconciliation)
    assert len(exceptions) == 2
    assert all(e.severity != "ERROR" for e in exceptions)


# ---------------------------------------------------------------------------
# run_dd_aggregation — manifest-level hard stops
# ---------------------------------------------------------------------------

def test_run_dd_aggregation_raises_when_unit_gross_acres_missing():
    manifest = UnitManifest(
        unit_name="TEST UNIT",
        represented_interest=RepresentedInterest(current_wi="0.9975", current_nri="0.788"),
    )
    rows = [LeaseTractRow("L1", Fraction(100), Fraction(1), Fraction(1), Fraction(0))]

    with pytest.raises(AggregationError, match="unit_gross_acres"):
        run_dd_aggregation(manifest, rows)


def test_run_dd_aggregation_raises_when_represented_interest_missing():
    manifest = UnitManifest(unit_name="TEST UNIT", unit_gross_acres="200")
    rows = [LeaseTractRow("L1", Fraction(100), Fraction(1), Fraction(1), Fraction(0))]

    with pytest.raises(AggregationError, match="represented_interest"):
        run_dd_aggregation(manifest, rows)


def test_run_dd_aggregation_end_to_end():
    manifest = UnitManifest(
        unit_name="TEST UNIT",
        unit_gross_acres="200",
        represented_interest=RepresentedInterest(
            current_wi="0.5", current_nri="0.4375", basis="leasehold"
        ),
    )
    rows = [
        LeaseTractRow("L1", Fraction(100), Fraction(1), Fraction(1), Fraction(1, 8)),
        LeaseTractRow("L2", Fraction(100), Fraction(0), Fraction(1), Fraction(1, 8)),
    ]
    aggregation, reconciliation, exceptions = run_dd_aggregation(manifest, rows)

    assert aggregation.seller_wi == Fraction(1, 2)
    assert reconciliation.wi_status == "PASS"
    assert exceptions == []


# ---------------------------------------------------------------------------
# derive_wi_from_nri_formula — recover the WORKING interest from an NRI
# calculation formula, checksum-validated against the printed NRI.
# ---------------------------------------------------------------------------

def test_derive_wi_from_cox_eog_formula_matches_checksum():
    # EOG's Cox row: "[(49.768518% x 4/5) plus (35.185186% x 75%)]" with the
    # printed NRI .66203704 -> working interest .84953704 (sum of leading %s).
    formula = "[(49.768518% x 4/5) plus (35.185186% x 75%)]"
    stated_nri = parse_fraction_text(".66203704")
    wi = derive_wi_from_nri_formula(formula, stated_nri)
    assert wi is not None
    expected_wi = Fraction("0.49768518") + Fraction("0.35185186")
    assert wi == expected_wi
    assert abs(float(wi) - 0.84953704) < 1e-8


def test_derive_wi_refuses_when_checksum_mismatch():
    formula = "[(49.768518% x 4/5) plus (35.185186% x 75%)]"
    # Wrong stated NRI -> refuse rather than fabricate.
    assert derive_wi_from_nri_formula(formula, parse_fraction_text(".5")) is None


def test_derive_wi_refuses_single_factor_term():
    # A bare "(1/4)" is not an NRI calculation (no revenue factor) — dropping
    # the only factor would fabricate a working interest.
    assert derive_wi_from_nri_formula("(1/4)", Fraction(1, 4)) is None


def test_derive_wi_without_checksum_still_requires_wi_gt_nri():
    wi = derive_wi_from_nri_formula("(50% x 3/4) plus (25% x 4/5)", None)
    # NRI = 0.375 + 0.20 = 0.575 ; WI = 0.50 + 0.25 = 0.75
    assert wi == Fraction("0.75")


# ---------------------------------------------------------------------------
# Basis-aware reconciliation — never delta-compare leasehold to wellbore.
# ---------------------------------------------------------------------------

def test_wellbore_basis_yields_na_not_warning():
    manifest = UnitManifest(
        unit_name="TEST UNIT",
        unit_gross_acres="100",
        represented_interest=RepresentedInterest(
            current_wi="0.992486", current_nri="0.748610", basis="wellbore"
        ),
    )
    # Leasehold aggregate ~0.85 differs from wellbore 0.992486 by design.
    rows = [LeaseTractRow("L1", Fraction(100), Fraction(1), Fraction("0.85"), Fraction(1, 8))]
    aggregation, reconciliation, exceptions = run_dd_aggregation(manifest, rows)

    assert reconciliation.wi_status == "N/A"
    assert reconciliation.nri_status == "N/A"
    assert reconciliation.wi_delta == Fraction(0)
    assert exceptions == []  # no false WARNING
    assert reconciliation.computed_wi == Fraction("0.85")
    assert reconciliation.represented_wi == Fraction("0.992486")


def test_leasehold_basis_still_reconciles_and_can_warn():
    manifest = UnitManifest(
        unit_name="TEST UNIT",
        unit_gross_acres="100",
        represented_interest=RepresentedInterest(
            current_wi="0.5", current_nri="0.4", basis="leasehold"
        ),
    )
    rows = [LeaseTractRow("L1", Fraction(100), Fraction(1), Fraction("0.85"), Fraction(1, 8))]
    _agg, reconciliation, exceptions = run_dd_aggregation(manifest, rows)
    assert reconciliation.wi_status == "WARNING"  # 0.85 vs 0.5
    assert any(e.code == "DD_WI_RECONCILIATION" for e in exceptions)
