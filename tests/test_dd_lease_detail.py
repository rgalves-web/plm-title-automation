"""Per-lease MI/WI mapping + royalty carry-over (Collin items 1-2)."""
from __future__ import annotations

from fractions import Fraction

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
