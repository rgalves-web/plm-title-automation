"""PR-5 — sources that prove terms, and the gap-hunter.

The requirement tests are written from the real Josh B opinions, because the
whole point of S5 is reading like an examiner rather than like a text search.
"""
from __future__ import annotations

import pytest

from src.knowledge.fetch_brief import blocks_certification
from src.knowledge.gap_hunter import (Gap, counties_in, feeds_of,
                                      hunt_post_cert_leases, hunt_requirements,
                                      mark_inference, parse_requirements,
                                      subject_of, survives)
from src.knowledge.lease_disposition import STATUS_TERMS_SOURCED, dispose
from src.knowledge.loader import load_knowledge
from src.knowledge.term_source import norm_recording, resolve
from src.knowledge.to_schedule import parse_schedule, unrecorded_in_schedule

K = load_knowledge()


# --- 1. an of-record document that states a term is the source of it -------

def _opinion(entries) -> dict:
    return {"file": "T-O ORIG A-319.PDF", "classified_as": "title_opinion",
            "of_record": {"status": "recorded"}, "extracted": {},
            "proves": entries}


def test_the_rule_is_general_and_lives_in_the_taxonomy_for_more_than_memoranda():
    # It was written as a memorandum rule. What makes a document a source is
    # being of record and stating the term — not being a memorandum.
    with_rule = {name for name, cat in K.taxonomy.categories.items()
                 if cat.proves_terms is not None}
    assert {"lease_memorandum", "title_opinion"} <= with_rule


def test_an_opinion_schedule_proves_the_terms_of_a_lease_it_recites():
    doc = _opinion([{"recording_book_page": "Volume 438, page 150", "page": 14,
                     "terms": {"lessor": "Austin Presbyterian Theological "
                                         "Seminary", "royalty": "1/5",
                               "instrument_date": "March 31, 2008"}}])
    out = resolve({"recording_book_page": "Vol. 438, Pg. 150"}, [doc], K)
    assert out.proved["royalty"].value == "1/5"
    assert out.proved["royalty"].citation() == "T-O ORIG A-319.PDF p.14"


def test_a_lease_the_opinion_does_not_schedule_gets_nothing_from_it():
    # Coverage is never assumed from the opinion merely being in the folder.
    doc = _opinion([{"recording_book_page": "Volume 438, page 150", "page": 14,
                     "terms": {"royalty": "1/5"}}])
    assert not resolve({"recording_book_page": "Vol. 999, Pg. 1"}, [doc], K).proved


def test_matching_is_by_recording_and_never_by_a_name():
    # The same lessor holds leases in several units; a name match imports
    # another unit's terms and looks entirely convincing while doing it.
    doc = _opinion([{"recording_book_page": "Volume 1, page 1",
                     "lessor": "Mike Schmidt", "page": 14,
                     "terms": {"royalty": "1/4"}}])
    out = resolve({"recording_book_page": "Vol. 439, Pg. 450",
                   "lessor": "Mike Schmidt"}, [doc], K)
    assert not out.proved


def test_a_document_that_is_not_of_record_proves_nothing():
    doc = _opinion([{"recording_book_page": "Volume 438, page 150", "page": 14,
                     "terms": {"royalty": "1/5"}}])
    doc["of_record"] = {"status": "not_recorded", "reason": "internal memo"}
    assert not resolve({"recording_book_page": "Vol. 438, Pg. 150"}, [doc], K).proved


def test_the_instrument_outranks_a_recital_of_it_and_the_conflict_is_kept():
    lease = {"file": "LEASE.TIF", "classified_as": "lease_ogl",
             "of_record": {"status": "recorded"},
             "evidence": {"page": 1, "quote": "PAID-UP OIL, GAS AND MINERAL LEASE"},
             "extracted": {"recording": "Vol. 438, Pg. 150", "royalty": "1/6"}}
    doc = _opinion([{"recording_book_page": "Volume 438, page 150", "page": 14,
                     "terms": {"royalty": "1/5"}}])
    out = resolve({"recording_book_page": "Vol. 438, Pg. 150"}, [lease, doc], K)
    assert out.proved["royalty"].value == "1/6"
    assert out.conflicts and out.conflicts[0]["term"] == "royalty"


def test_silence_is_a_named_blank_and_never_a_value():
    doc = _opinion([{"recording_book_page": "Volume 438, page 150", "page": 14,
                     "terms": {"royalty": "1/5"}}])
    out = resolve({"recording_book_page": "Vol. 438, Pg. 150"}, [doc], K)
    assert out.unproved["bonus"] == "doc_nao_localizado"


def test_a_missing_instrument_with_sourced_terms_is_a_delivery_not_a_search():
    doc = _opinion([{"recording_book_page": "Volume 438, page 150", "page": 14,
                     "terms": {"lessor": "A. P. Seminary", "royalty": "1/5"}}])
    d = dispose("0220750-005", "Vol. 438, Pg. 150",
                [{"file": "LETTER.PDF", "classified_as": "correspondence",
                  "evidence": {}, "of_record": {}}], K, extra_sources=[doc])
    assert d.status == STATUS_TERMS_SOURCED
    assert d.proved_terms["royalty"]["value"] == "1/5"
    assert d.defect["label"] == "MISSING LEASE"
    assert "delivery the Seller owes" in d.note


def test_the_schedule_parser_keeps_what_the_opinion_calls_unrecorded():
    blocks = [{"page": 27, "text": "LEASE 36\nDATE: April 9, 2008\n"
                                   "RECORDING: Unrecorded.\nLESSOR: Nan Kirkendahl\n"
                                   "ROYALTY: 1/5\n"}]
    schedule = parse_schedule(blocks)
    assert schedule[0]["lease_no"] == "36"
    # Nobody can fetch a recording that does not exist; saying so is the finding.
    assert unrecorded_in_schedule(schedule)
    assert not norm_recording(schedule[0]["recording_book_page"])


# --- 2. the gap-hunter -----------------------------------------------------

ECTOR = [{"page": 6, "text":
          "ITEM 4\n"
          "TITLE: Unrecorded Probates\n"
          "COMMENT: Charles F. Yentes died June 8, 1957, leaving a will probated "
          "in Cause No. 1449, County Court, Ector County, Texas.\n"
          "REQUIREMENT: Obtain certified copies of the probate proceedings and "
          "file them in the Real Records of Montague County, Texas.\n"
          "COUNTY: Ector County, Montague County\n"
          "CAUSE_NO: Cause No. 1449, Cause No. 3734-A, Cause No. 16915-02\n"
          "LEASES: NONE\nPARTIES: Charles F. Yentes; J. C. McConnell\n"}]


def test_the_probate_county_comes_from_the_requirement_not_from_the_land():
    # The land is in Montague. These probates are of record in Ector, ~350 miles
    # away, because that is where the decedents lived. An item that says
    # "probate, Montague County" sends someone to the wrong courthouse.
    gaps = hunt_requirements(parse_requirements(ECTOR),
                             opinion="T-O A-669 50AC", land_county="Montague")
    assert len(gaps) == 1
    g = gaps[0]
    assert g.county == "Ector"
    assert "NOT Montague" in g.detail
    for cause in ("1449", "3734-A", "16915-02"):
        assert cause in g.cause_no


def test_the_land_county_is_not_reported_as_the_records_county():
    gaps = hunt_requirements(parse_requirements(ECTOR),
                             opinion="x", land_county="Montague")
    assert "Montague" not in gaps[0].county


def test_a_satisfied_or_advisory_requirement_is_not_emitted():
    blocks = [{"page": 20, "text":
               "ITEM 15\nTITLE: Taxes\n"
               "COMMENT: A Tax Certificate indicates taxes have been paid.\n"
               "REQUIREMENT: None, advisory only.\nCOUNTY: NONE\n"
               "CAUSE_NO: NONE\nLEASES: NONE\nPARTIES: NONE\n"}]
    assert hunt_requirements(parse_requirements(blocks), opinion="x",
                             land_county="Montague") == []


def test_requirements_are_tagged_by_opinion_because_every_opinion_starts_at_one():
    gaps = hunt_requirements(parse_requirements(ECTOR), opinion="x",
                             land_county="Montague", tag="A-669 Tract 1")
    assert gaps[0].subject.startswith("[A-669 Tract 1] Req 4")


@pytest.mark.parametrize("text,expected", [
    ("Obtain a quitclaim from the heirs", "quitclaim"),
    ("probated in Cause No. 1449", "probate"),
    ("We assumed this was the same person", "identity"),
    ("obtain an affidavit of non-production", "nonproduction"),
    ("A Tax Certificate dated January 29", "tax"),
])
def test_the_requirement_subject_comes_from_its_language(text, expected):
    assert subject_of(text) == expected


def test_only_ownership_curative_blocks_certification():
    assert blocks_certification(feeds_of("probate"))
    assert blocks_certification(feeds_of("quitclaim"))
    assert not blocks_certification(feeds_of("runsheet"))
    assert not blocks_certification(feeds_of("possession"))


def test_counties_are_read_out_of_prose_without_swallowing_record_words():
    assert counties_in("Real Records of Ector County and Wichita County") == \
        ["Ector", "Wichita"]


def test_a_lease_after_every_cert_date_is_a_gap():
    gaps = hunt_post_cert_leases(
        {"0220750-008": "Vol. 610, Pg. 245"},
        {"0220750-008": "April 9, 2011"},
        {"T-O A-319": "May 21, 2010"})
    assert len(gaps) == 1
    assert "no opinion has examined this lease" in gaps[0].detail


def test_a_lease_inside_the_cert_window_is_not_a_gap():
    assert hunt_post_cert_leases({"x": "Vol. 1, Pg. 1"}, {"x": "March 31, 2008"},
                                 {"T-O": "May 21, 2010"}) == []


# --- inference discipline --------------------------------------------------

def test_an_inference_must_name_what_would_refute_it():
    g = mark_inference(Gap(kind="inference", subject="s", detail="d", proof="p"),
                       attack="the deed's calls would show the tract inside")
    assert g.inference and g.confidence == "inferred" and g.attack


def test_an_inference_that_loses_its_attack_is_withdrawn_not_softened():
    g = mark_inference(Gap(kind="inference", subject="s", detail="d", proof="p"),
                       attack="a")
    assert survives(g, refuted=True) is None


def test_a_stated_fact_is_not_touched_by_the_attack_machinery():
    g = Gap(kind="live_requirement", subject="s", detail="d", proof="p")
    assert survives(g, refuted=True) is g
