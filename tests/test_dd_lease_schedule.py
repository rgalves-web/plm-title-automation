"""Lease-schedule extraction merge + pooled-lease MI fallback (Collin item 3)."""
from __future__ import annotations

from fractions import Fraction

from src.dd.lease_detail import build_lease_details, _leading_fraction
from src.dd.manifest import LeaseRef
from src.dd.title_opinion_parser import (
    TOLeaseBlock,
    TOPartyInterest,
    TOTract,
    TitleOpinionExtraction,
    _LEASE_SCHEDULE_TOOL,
)
from src.llm_extractor import LLMFieldResult


def test_lease_schedule_tool_shape():
    # The dedicated schedule tool emits only leases (bounded output).
    props = _LEASE_SCHEDULE_TOOL["input_schema"]["properties"]
    assert set(props) == {"leases"}
    item = props["leases"]["items"]["properties"]
    assert "lease_identifier" in item and "interest_covered" in item and "royalty" in item


def test_leading_fraction_from_prose():
    assert _leading_fraction("1/2 mineral interest") == Fraction(1, 2)
    assert _leading_fraction("62.5% working interest") == Fraction("0.625")
    assert _leading_fraction("no fraction here") is None


def _f(v):
    return LLMFieldResult(value=v, confidence=1.0)


def test_pooled_lease_mi_from_lease_block_interest_covered():
    # Kramer tract: the lease's lessor (Joan B Scott Maxwell) is NOT a named
    # mineral owner (owner is 'Kramer Mineral Trust'); MI must come from the
    # lease-analysis block's interest_covered.
    tract = TOTract(
        tract_legal_description=_f("22.3333 acres A-122 Blk 7"),
        mineral_owners=[TOPartyInterest(party="Kramer Mineral Trust", fraction_text="3/4", confidence=1.0)],
        leases=[TOLeaseBlock(
            lessor=_f("Joan B. Scott Maxwell"), lease_date=_f("May 8, 2006"),
            recording_info=_f("Vol 463, Page 68"), interest_covered=_f("1/4 mineral interest"),
            royalty=_f("1/5"), primary_term=_f("3 years"))],
    )
    controlling = {"T-O_KRAMER": TitleOpinionExtraction(file_number="T-O_KRAMER", tracts=[tract])}
    d = build_lease_details([LeaseRef(lease_no="0190122-001", lessor="JOAN B SCOTT MAXWELL")],
                            controlling)[0]
    assert d.mi_value == Fraction(1, 4)      # from interest_covered, not the owner
    assert d.wi_value == Fraction(1)
    assert d.royalty == "1/5"
    assert "lease-analysis" in d.source


def test_direct_mineral_owner_still_wins_over_block():
    # When the lessor IS a mineral owner, use the MINERALS fraction directly.
    tract = TOTract(
        tract_legal_description=_f("140.9963 acres A-122"),
        mineral_owners=[TOPartyInterest(party="Lynn W. Cox", fraction_text="1/2", confidence=1.0)],
        leases=[TOLeaseBlock(lessor=_f("Lynn W. Cox"), interest_covered=_f("1/3 mineral interest"))],
    )
    controlling = {"T-O_COX": TitleOpinionExtraction(file_number="T-O_COX", tracts=[tract])}
    d = build_lease_details([LeaseRef(lease_no="0220344-013", lessor="LYNN W COX")], controlling)[0]
    assert d.mi_value == Fraction(1, 2)  # MINERALS, not the block's 1/3
