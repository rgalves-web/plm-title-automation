"""DPU + Amendment as a first-class source (Maxwell lessons item 3).

Fixture text is transcribed from the REAL recorded instruments
(K1400813: "UNIT DEC - REC.TIF" 8pp, "UNIT DEC AMENDMENT - REC.TIF" 3pp),
including their OCR quirks — the mangled title dash and the DPU's own blank
recording reference for lease -024.
"""
from __future__ import annotations

import pytest

from src.dd.dpu_parser import (
    merge_dpu_and_amendments,
    normalize_lease_no,
    parse_dpu,
    parse_exhibit_a,
    parse_vol_page,
)

_DPU_TEXT = """
. VOL. 491 Page 160
DECLARATION OF POOLED UNIT �- MAXWELL A UNIT
STATE OF TEXAS S
COUNTY OF MONTAGUE
This Declaration of Pooled Unit is executed by the undersigned ...
shall be effective as of August 12, 2009, (the Effective Date)
\f
. VOL. 491 Page 162
EXHIBIT "A"
Attached to and made a part of that certain Declaration of Pooled Unit:
Maxwell A Unit dated effective August 12, 2009.
EOG Lease Number: 190122-001
Lease Date: August 23, 2006
Lessor: Joan B. Maxwell
Original Lessee: EOG Resources, Inc.
Recording Information: Volume 402, Page 50, Montague County, Texas
EOG Lease Number: 220335-004
Lease Date: August 7, 2008
Lessor: W.S. Brumbaugh, Carolyn Belew, Billy Ray Caldwell, Linda
Pritchard, Lovene Brumbaugh and Larry Brumbaugh
Original Lessee: EOG Resources, Inc.
Recording Information: Volume 457, Page 254, Montague County, Texas
EOG Lease Number: 220344-024
Lease Date: June 17, 2009
Lessor: American Diabetes Association
Original Lessee: EOG Resources, Inc.
Recording Information: Volume__, Page__, Montague County, Texas
"""

# The amendment's 7 added leases — the kickoff's ground truth, verbatim shape.
_AMENDMENT_TEXT = """
. . 116856 VOL 574 PAGE 830
AMENDMENT OF DECLARATION OF POOLED UNIT -
MAXWELL A UNIT
WHEREAS, by instrument styled, "Declaration of Pooled Unit - MAXWELL A UNIT,"
effective August 12, 2009, and recorded in Book 491, at Page 160 ...
WHEREAS, EOG Resources, Inc. determined that one or more leases within the current
boundary were inadvertently excluded from Exhibit "A".
EOG Lease Number: 222854-000
Lease Date: May 3, 2011
Lessor: The State of Texas
Original Lessee: EOG Resources, Inc.
Recording Information: Vol. 571, Pg. 82, Real Records, Montague County, Texas
EOG Lease Number: 220344-025
Lease Date: January 14, 2010
Lessor: Jon S. Brown
Original Lessee: EOG Resources, Inc.
Recording Information: Vol. 507, Pg. 775, Real Records, Montague County, Texas
EOG Lease Number: 220344-026
Lease Date: January 14, 2010
Lessor: JDMI, LLC., by James H. Davis, Member
Original Lessee: EOG Resources, Inc.
Recording Information: Vol. 507, Pg. 751, Real Records, Montague County, Texas
EOG Lease Number: 220344-027
Lease Date: June 4, 2010
Lessor: Loy D. Self
Original Lessee: EOG Resources, Inc.
Recording Information: Vol. 526, Pg. 839, Real Records, Montague County, Texas
EOG Lease Number: 220344-028
Lease Date: October 15, 2010
Lessor: Lewis Bowland
Original Lessee: EOG Resources, Inc.
Recording Information: Vol. 541, Pg. 32, Real Records, Montague County, Texas
EOG Lease Number: 220344-031
Lease Date: March 16, 2011
Lessor: Bob Bowland
Original Lessee: EOG Resources, Inc.
Recording Information: Vol. 564, Pg. 390, Real Records, Montague County, Texas
EOG Lease Number: 220344-032
Lease Date: March 16, 2011
Lessor: Tabby "Tab" L. Bowland
Original Lessee: EOG Resources, Inc.
Recording Information: Vol. 566, Pg. 664, Real Records, Montague County, Texas
"""

# Ground truth: lease -> (book, page) added by the Amendment.
_AMENDMENT_ADDED = {
    "0220344-025": ("507", "775"),
    "0220344-026": ("507", "751"),
    "0220344-027": ("526", "839"),
    "0220344-028": ("541", "32"),
    "0220344-031": ("564", "390"),
    "0220344-032": ("566", "664"),
    "0222854-000": ("571", "82"),
}


def test_lease_numbers_normalize_to_canonical_form():
    assert normalize_lease_no("190122-001") == "0190122-001"
    assert normalize_lease_no("0190122-001") == "0190122-001"
    assert normalize_lease_no("EOG Lease Number: 220344-025") == "0220344-025"
    assert normalize_lease_no("no lease here") is None


@pytest.mark.parametrize("text, expected", [
    ("Volume 402, Page 50, Montague County, Texas", ("402", "50")),
    ("Vol. 571, Pg. 82, Real Records, Montague County, Texas", ("571", "82")),
    ("recorded in Book 491, at Page 160, of the Real Records", ("491", "160")),
    ("Volume__, Page__, Montague County, Texas", (None, None)),
])
def test_vol_page_forms_both_instruments_use(text, expected):
    assert parse_vol_page(text) == expected


def test_dpu_header_parses_through_ocr_mangled_dash():
    dpu = parse_dpu(_DPU_TEXT)
    assert dpu.unit_name == "MAXWELL A UNIT"
    assert dpu.effective_date == "August 12, 2009"
    assert (dpu.recorded_book, dpu.recorded_page) == ("491", "160")
    assert not dpu.is_amendment


def test_amendment_is_identified_as_an_amendment():
    amendment = parse_dpu(_AMENDMENT_TEXT)
    assert amendment.is_amendment
    assert (amendment.recorded_book, amendment.recorded_page) == ("574", "830")


def test_exhibit_a_entry_carries_record_book_and_page():
    leases = {x.lease_no: x for x in parse_exhibit_a(_DPU_TEXT)}
    joan = leases["0190122-001"]
    # v5's Ownership Report K8/L8 are exactly these.
    assert (joan.record_book, joan.record_page) == ("402", "50")
    assert joan.lessor == "Joan B. Maxwell"
    assert joan.lease_date == "August 23, 2006"


def test_multi_line_lessor_is_captured_whole():
    leases = {x.lease_no: x for x in parse_exhibit_a(_DPU_TEXT)}
    lessor = leases["0220335-004"].lessor
    assert lessor.startswith("W.S. Brumbaugh") and lessor.endswith("Larry Brumbaugh")


def test_blank_recording_in_the_instrument_is_not_fabricated():
    # The DPU itself prints "Volume__, Page__" — the blank is the source's.
    leases = {x.lease_no: x for x in parse_exhibit_a(_DPU_TEXT)}
    entry = leases["0220344-024"]
    assert entry.record_book is None and entry.record_page is None
    assert not entry.has_recording


@pytest.mark.parametrize("lease_no, expected", sorted(_AMENDMENT_ADDED.items()))
def test_amendment_added_leases_with_recording(lease_no, expected):
    leases = {x.lease_no: x for x in parse_exhibit_a(_AMENDMENT_TEXT)}
    assert lease_no in leases, "amendment lease missing"
    assert (leases[lease_no].record_book, leases[lease_no].record_page) == expected


def test_merge_adds_every_amendment_lease_and_notes_why():
    dpu = parse_dpu(_DPU_TEXT, source="UNIT DEC - REC.TIF")
    amendment = parse_dpu(_AMENDMENT_TEXT, source="UNIT DEC AMENDMENT - REC.TIF")
    merged, notes = merge_dpu_and_amendments(dpu, [amendment])
    by_lease = {x.lease_no: x for x in merged}
    # Original Exhibit A leases survive ...
    assert "0190122-001" in by_lease
    # ... and all 7 inadvertently-excluded leases are added, with recordings.
    for lease_no, expected in _AMENDMENT_ADDED.items():
        assert (by_lease[lease_no].record_book, by_lease[lease_no].record_page) == expected
    assert len(notes) == len(_AMENDMENT_ADDED)
    assert all("inadvertently excluded" in n for n in notes)


def test_amendment_restating_a_recording_wins_and_is_noted():
    dpu = parse_dpu(_DPU_TEXT, source="dpu")
    restated = parse_dpu(
        "AMENDMENT OF DECLARATION OF POOLED UNIT - MAXWELL A UNIT\n"
        "EOG Lease Number: 190122-001\nLease Date: August 23, 2006\n"
        "Lessor: Joan B. Maxwell\nOriginal Lessee: EOG Resources, Inc.\n"
        "Recording Information: Volume 999, Page 1, Montague County, Texas\n",
        source="amendment")
    merged, notes = merge_dpu_and_amendments(dpu, [restated])
    joan = {x.lease_no: x for x in merged}["0190122-001"]
    assert (joan.record_book, joan.record_page) == ("999", "1")  # later instrument wins
    assert any("restates recording" in n and "verify" in n for n in notes)


def test_amendment_with_no_new_leases_changes_nothing():
    dpu = parse_dpu(_DPU_TEXT, source="dpu")
    merged, notes = merge_dpu_and_amendments(dpu, [])
    assert len(merged) == len(dpu.leases) and notes == []
