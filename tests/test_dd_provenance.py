"""Cell-level provenance + anchored verification.

The anchor must be found by SEARCHING the source — the summarizer never
nominates its own proof, or we verify the LLM against itself and learn nothing.
"""
from __future__ import annotations

import pytest

from src.dd.provenance import (
    Anchor,
    CellSource,
    ProvenanceStore,
    StructuredSource,
    check_completeness,
    check_fidelity,
    facts_in,
    locate_anchor,
    locate_page,
)

_LEASE = """Page one has the granting clause and nothing about pooling.
\fLessee is hereby granted the right, at its option, to pool or unitize any land covered by this
lease. Units for oil shall not exceed 40 acres plus a tolerance of 10%, and units for gas or
horizontal completions shall not exceed 640 acres plus a tolerance of 10%, unless a larger unit
is required by governmental authority. Lessee shall have no right to pool below the base of the
Barnett Shale without the consent of Lessor.
\fPage three is the acknowledgement."""

_FAITHFUL = ("Lessee may pool; oil units not to exceed 40 acres +10% tolerance, "
             "gas or horizontal completions 640 acres +10% tolerance")


# --- the anchor is located independently -----------------------------------

def test_anchor_is_found_on_the_page_that_supports_the_value():
    anchor = locate_anchor(_LEASE, _FAITHFUL)
    assert anchor is not None
    assert anchor.page == 2                      # searched for, not asserted
    assert "40 acres" in anchor.quote


def test_locate_page_agrees_with_the_anchor():
    assert locate_page(_LEASE, _FAITHFUL) == 2


def test_an_unsupported_value_gets_no_anchor():
    # NO_ANCHOR is surfaced, never papered over with the extractor's own claim.
    assert locate_anchor(_LEASE, "the lease is silent as to pooling authority") is None


def test_an_empty_value_has_no_anchor():
    assert locate_anchor(_LEASE, "") is None
    assert locate_anchor("", "anything") is None


def test_the_summarizer_does_not_choose_its_own_page():
    # Even if an extractor claimed p.3, the search puts the anchor on p.2.
    assert locate_anchor(_LEASE, _FAITHFUL).page == 2


# --- fidelity: a summary may not assert what its anchor lacks ---------------

def test_facts_in_picks_up_numbers_fractions_and_percentages():
    got = facts_in("oil 40 acres +10%, gas 640 acres, royalty 1/5")
    assert {"40", "10%", "640", "1/5"} <= got


def test_a_faithful_summary_invents_nothing():
    anchor = locate_anchor(_LEASE, _FAITHFUL)
    assert check_fidelity(_FAITHFUL, anchor.quote) == set()


def test_an_invented_number_is_caught():
    invented = _FAITHFUL.replace("640 acres", "999 acres")
    anchor = locate_anchor(_LEASE, invented)
    assert "999" in check_fidelity(invented, anchor.quote)


def test_a_swapped_acreage_is_caught():
    # 40 -> 400: the kind of error that reads as plausible and is not.
    wrong = _FAITHFUL.replace("40 acres", "400 acres")
    anchor = locate_anchor(_LEASE, wrong)
    assert "400" in check_fidelity(wrong, anchor.quote)


# --- completeness: a dropped material term is surfaced, never lost ----------

def test_a_dropped_depth_limitation_is_flagged():
    anchor = locate_anchor(_LEASE, _FAITHFUL)
    dropped = check_completeness(_FAITHFUL, anchor.quote)
    assert "consent requirement" in dropped      # "without the consent of Lessor"


def test_a_summary_that_keeps_the_material_terms_is_clean():
    full = _FAITHFUL + "; no right to pool below the Barnett Shale without the consent of Lessor"
    assert "consent requirement" not in check_completeness(full, _LEASE)


def test_completeness_says_nothing_when_the_anchor_has_no_material_terms():
    assert check_completeness("40 acres", "units of 40 acres") == []


# --- the store is internal, and cites document + page ----------------------

def test_store_round_trips_and_cites_document_and_page():
    store = ProvenanceStore()
    store.put("Lease Review", "O2",
              CellSource(document="LEASE.TIF", page=2, quote="units for oil ... 40 acres",
                         method="search", field_name="pooling clause"))
    source = store.get("Lease Review", "O2")
    assert source.cite() == "LEASE.TIF p.2"
    assert len(store) == 1


def test_store_emits_cell_level_audit_rows():
    store = ProvenanceStore()
    store.put("Ownership Report", "S16",
              CellSource(document="T-O SUPP COX.PDF", page=5, quote="[(1/3 x 1/9)] .01736111",
                         method="search", field_name="MI Value"))
    rows = store.audit_rows()
    assert rows[0][0] == "Ownership Report" and rows[0][1] == "S16"
    assert "T-O SUPP COX.PDF p.5" in rows[0][3]


def test_a_structured_source_is_a_real_citation_not_a_gap():
    # A lease number legitimately comes from the XREF; that is re-readable.
    source = StructuredSource(workbook="Lease to Well XREF.xlsx", sheet="Sheet1",
                              row=42, column="B", field_name="lease_no")
    assert source.cite() == "Lease to Well XREF.xlsx[Sheet1]!B42"
