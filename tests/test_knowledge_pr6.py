"""PR-6 — field-level blanks, form inheritance, frames, and the kit.

Each test is a defect the Josh B cold run actually produced, checked against the
hand-built DDR built from the same title opinion.
"""
from __future__ import annotations

from pathlib import Path

from src.knowledge.kit_builder import (NEVER_SHIPS, SCREEN_CAPTURE_SUFFIXES,
                                       BuildResult, CellWrite, _status_reason,
                                       is_shippable)
from src.knowledge.lease_disposition import STATUS_OF_RECORD, dispose
from src.knowledge.loader import load_knowledge
from src.knowledge.term_source import _is_pointer, resolve
from src.knowledge.to_schedule import (apply_form_references, form_references,
                                       parse_schedule)

K = load_knowledge()


# --- form inheritance ------------------------------------------------------

FORM_PAGES = ["", "", "",
              "Leases 10 - 23 use the same form as Lease 9, and only those "
              "provisions differing from Lease 9 are included below.",
              "Leases 26 - 32 use the same form as Lease 10, and only those "
              "provisions differing from Lease 10 are included below:"]


def test_the_opinion_states_the_form_reference_so_it_is_read_not_inferred():
    refs = form_references(FORM_PAGES)
    assert refs["10"][0] == "9"
    assert refs["23"][0] == "9"
    assert refs["26"][0] == "10"
    assert "9" not in refs                    # the base does not point at itself


def test_unstated_form_terms_are_filled_from_the_base_lease_through_the_chain():
    schedule = [
        {"lease_no": "9", "page": 12, "recording_book_page": "Volume 1, page 1",
         "terms": {"royalty": "1/5", "term": "Three years"}, "quote": ""},
        {"lease_no": "10", "page": 14, "recording_book_page": "Volume 2, page 2",
         "terms": {}, "quote": ""},
        {"lease_no": "26", "page": 20, "recording_book_page": "Volume 3, page 3",
         "terms": {}, "quote": ""},
    ]
    out = {e["lease_no"]: e for e in apply_form_references(schedule, FORM_PAGES)}
    assert out["26"]["terms"]["royalty"] == "1/5"      # 26 -> 10 -> 9
    assert out["26"]["inherited"]["royalty"]["from_lease"] == "10"


def test_identity_never_inherits_because_two_leases_would_merge():
    schedule = [
        {"lease_no": "9", "page": 12, "recording_book_page": "Volume 1, page 1",
         "terms": {"lessor": "A. Base", "recording": "Volume 1, page 1",
                   "royalty": "1/5"}, "quote": ""},
        {"lease_no": "10", "page": 14, "recording_book_page": "Volume 2, page 2",
         "terms": {}, "quote": ""},
    ]
    out = {e["lease_no"]: e for e in apply_form_references(schedule, FORM_PAGES)}
    assert "lessor" not in out["10"]["terms"]
    assert "recording" not in out["10"]["terms"]


def test_a_borrowed_value_cites_both_pages_and_the_authorising_sentence():
    doc = {"file": "T-O.PDF", "classified_as": "title_opinion",
           "of_record": {"status": "recorded"}, "extracted": {},
           "proves": [{"recording_book_page": "Volume 2, page 2", "page": 14,
                       "terms": {"royalty": "1/5"},
                       "inherited": {"royalty": {"from_lease": "9",
                                                 "from_page": 12,
                                                 "authority_page": 4,
                                                 "quote": "Leases 10 - 23 use "
                                                          "the same form as "
                                                          "Lease 9"}}}]}
    out = resolve({"recording_book_page": "Vol. 2, Pg. 2"}, [doc], K)
    cite = out.proved["royalty"].citation()
    assert "form of Lease 9" in cite and "p.12" in cite and "p.4" in cite


# --- frames and pointers ---------------------------------------------------

def test_the_opinions_own_tract_numbering_never_becomes_a_ddr_value():
    # `LAND: Tract 2.` is the opinion's frame. Six cells read "Tract 2." on the
    # cold run while the hand DDR correctly carried the unit's tract text.
    doc = {"file": "T-O.PDF", "classified_as": "title_opinion",
           "of_record": {"status": "recorded"}, "extracted": {},
           "proves": [{"recording_book_page": "Volume 2, page 2", "page": 21,
                       "terms": {"legal_description": "Tract 2."}}]}
    out = resolve({"recording_book_page": "Vol. 2, Pg. 2"}, [doc], K)
    assert "legal_description" not in out.proved
    assert out.pointers["legal_description"]["value"] == "Tract 2."


def test_a_cross_reference_is_a_pointer_and_not_a_description():
    assert _is_pointer('SEE EXHIBIT "A" ATTACHED HERETO FOR DESCRIPTION OF LANDS')
    assert _is_pointer("as more fully described in the deed")
    assert not _is_pointer("155 acres out of the W. Scarborough Survey, A-669")


# --- field-level blanks ----------------------------------------------------

def test_a_present_instrument_still_reports_the_terms_it_does_not_state():
    # A missing royalty on a lease that IS in the file is a FIELD gap. Before
    # this it was indistinguishable from a missing lease.
    lease = {"file": "LEASE.TIF", "classified_as": "lease_ogl",
             "of_record": {"status": "recorded"},
             "evidence": {"page": 1, "quote": "OIL, GAS AND MINERAL LEASE"},
             "extracted": {"recording": "Vol. 1, Pg. 1", "lessor": "A. Lessor"}}
    d = dispose("0220604-002", "Vol. 1, Pg. 1", [lease], K)
    assert d.status == STATUS_OF_RECORD
    assert "lessor" in d.proved_terms
    assert "royalty" in d.unproved_terms          # named, not silently absent


def test_every_blank_carries_a_vocabulary_reason_even_with_no_per_term_one():
    reason = _status_reason({"status": "unidentified_documents_in_folder"})
    assert reason in K.valid_reasons()
    assert _status_reason({"status": "not_in_corpus"}) in K.valid_reasons()


def test_a_cell_is_a_value_with_a_citation_or_a_blank_with_a_reason():
    valued = CellWrite("Lease Review", 2, "J", "royalty", "1/5", "T-O.PDF p.14")
    blank = CellWrite("Lease Review", 3, "J", "royalty", "", "",
                      "doc_nao_localizado")
    orphan = CellWrite("Lease Review", 4, "J", "royalty", "", "", "")
    r = BuildResult(cells=[valued, blank, orphan])
    assert (r.evidenced, r.declared, r.orphan) == (1, 1, 1)
    assert not r.converged()
    assert BuildResult(cells=[valued, blank]).converged()


# --- what ships ------------------------------------------------------------

def test_a_screen_capture_of_a_document_is_not_the_document():
    # Portal screenshots classified as title_opinion at 0.95 filled the Title
    # Opinions folder with pictures. A kit that looks complete and is empty is
    # worse than one that declares the gap.
    shot = {"classified_as": "title_opinion", "of_record": {"status": "recorded"}}
    assert not is_shippable(Path("Captura de tela 2026-08-06.png"), shot)
    assert ".png" in SCREEN_CAPTURE_SUFFIXES


def test_internal_paper_stays_in_the_ledger_and_out_of_the_kit():
    for category in NEVER_SHIPS:
        assert not is_shippable(Path("x.pdf"), {"classified_as": category})


def test_a_sellers_ownership_report_ships_even_though_it_is_not_of_record():
    # Being of record is not the test; Seller Files are seller working papers.
    assert is_shippable(Path("OWNERSHIP REPORT.TIF"),
                        {"classified_as": "ownership_report",
                         "of_record": {"status": "not_recorded"}})
