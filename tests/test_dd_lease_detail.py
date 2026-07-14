"""Per-lease MI/WI mapping + royalty carry-over (Collin items 1-2)."""
from __future__ import annotations

from fractions import Fraction
from types import SimpleNamespace

from src.dd.dd_pipeline import enrich_lease_rows_with_details
from src.dd.lease_detail import build_lease_details
from src.dd.manifest import LeaseRef
from src.dd.title_opinion_parser import TOPartyInterest, TOTract, TitleOpinionExtraction
from src.llm_extractor import LLMFieldResult


def _cox_tract():
    return TOTract(
        tract_legal_description=LLMFieldResult(value="140.9963 acres, A-122 Blk 10 and 11", confidence=1.0),
        mineral_owners=[
            TOPartyInterest(party="Lynn W. Cox", fraction_text="1/2", confidence=1.0),
            TOPartyInterest(party="Richard T. Cox", fraction_text="1/4", confidence=1.0),
            TOPartyInterest(party="Sandra Lynn Cox Walker", fraction_text="1/4", confidence=1.0),
        ],
        royalty_owners=[TOPartyInterest(party="Lynn W. Cox", fraction_text="1/5", confidence=1.0)],
    )


def _controlling():
    return {"T-O_COX": TitleOpinionExtraction(file_number="T-O_COX", tracts=[_cox_tract()])}


def test_lessor_matched_to_mineral_owner_gives_mi_and_wi():
    leases = [LeaseRef(lease_no="0220344-013", lessor="LYNN W COX"),
              LeaseRef(lease_no="0220344-014", lessor="RICHARD COX")]
    details = {d.lease_no: d for d in build_lease_details(leases, _controlling())}
    assert details["0220344-013"].mi_value == Fraction(1, 2)
    assert details["0220344-013"].wi_value == Fraction(1)  # EOG full leasehold WI
    assert "MINERALS section" in details["0220344-013"].source
    assert details["0220344-014"].mi_value == Fraction(1, 4)


def test_royalty_carry_over_takes_precedence():
    leases = [LeaseRef(lease_no="0220344-013", lessor="LYNN W COX")]
    details = build_lease_details(leases, _controlling(),
                                  royalty_by_lease={"0220344-013": "1/4"})
    assert details[0].royalty == "1/4"  # carried over, not the tract's 1/5


def test_royalty_falls_back_to_tract_when_no_carryover():
    leases = [LeaseRef(lease_no="0220344-013", lessor="LYNN W COX")]
    details = build_lease_details(leases, _controlling())
    assert details[0].royalty == "1/5"  # tract royalty owner


def test_unmatched_lessor_leaves_mi_empty_with_note():
    leases = [LeaseRef(lease_no="0222854-000", lessor="ST TX MF-112592")]
    d = build_lease_details(leases, _controlling())[0]
    assert d.mi_value is None
    assert d.notes and "not matched" in d.notes[0]


def test_tract_gross_acres_uses_supplied_fn():
    leases = [LeaseRef(lease_no="0220344-013", lessor="LYNN W COX")]
    d = build_lease_details(leases, _controlling(),
                            tract_gross_fn=lambda t: Fraction("140.9963"))[0]
    assert d.tract_gross_acres == Fraction("140.9963")


# --- Collin item-1 regression: per-owner MI must stay distinct, never flattened ---

def _distinct_cox_tract():
    """Three Cox mineral owners with genuinely different fractions."""
    return TOTract(
        tract_legal_description=LLMFieldResult(value="Cox tract, A-122", confidence=1.0),
        mineral_owners=[
            TOPartyInterest(party="John A. Cox", fraction_text="1/36", confidence=1.0),
            TOPartyInterest(party="Sandra Lynn Walker", fraction_text="5/72", confidence=1.0),
            TOPartyInterest(party="Lynn W. Cox", fraction_text="5/36", confidence=1.0),
        ],
    )


def test_cox_owners_get_distinct_per_owner_mi():
    leases = [LeaseRef(lease_no="L1", lessor="JOHN A COX"),
              LeaseRef(lease_no="L2", lessor="SANDRA LYNN WALKER"),
              LeaseRef(lease_no="L3", lessor="LYNN W COX")]
    controlling = {"TO_COX": TitleOpinionExtraction(file_number="TO_COX", tracts=[_distinct_cox_tract()])}
    d = {x.lease_no: x for x in build_lease_details(leases, controlling)}
    assert d["L1"].mi_value == Fraction(1, 36)
    assert d["L2"].mi_value == Fraction(5, 72)
    assert d["L3"].mi_value == Fraction(5, 36)
    # All three are authoritative owner matches and must be distinct.
    assert all(x.mi_source == "mineral_owner" for x in d.values())
    assert len({x.mi_value for x in d.values()}) == 3


def test_enrich_owner_match_overwrites_a_flattened_mi():
    """The regression: rows arrive pre-flattened to one owner's fraction (5/36).
    The name-matched per-owner MI must overwrite that uniform value."""
    leases = [LeaseRef(lease_no="L1", lessor="JOHN A COX"),
              LeaseRef(lease_no="L2", lessor="SANDRA LYNN WALKER"),
              LeaseRef(lease_no="L3", lessor="LYNN W COX")]
    controlling = {"TO_COX": TitleOpinionExtraction(file_number="TO_COX", tracts=[_distinct_cox_tract()])}
    # Simulate the flattened state a lease-block match used to leave behind.
    rows = [{"lease_no": lr.lease_no, "lessor": lr.lessor, "mi_value": Fraction(5, 36)}
            for lr in leases]
    manifest = SimpleNamespace(leases=leases, expected_seller_wi=None, unit_gross_acres=None)
    reconciliation = SimpleNamespace(computed_wi=None, wi_status="NOT_COMPUTED")
    enrich_lease_rows_with_details(rows, manifest, controlling, reconciliation)
    by_lease = {r["lease_no"]: r["mi_value"] for r in rows}
    assert by_lease["L1"] == Fraction(1, 36)   # overwritten, not the flattened 5/36
    assert by_lease["L2"] == Fraction(5, 72)
    assert by_lease["L3"] == Fraction(5, 36)
    assert len(set(by_lease.values())) == 3
