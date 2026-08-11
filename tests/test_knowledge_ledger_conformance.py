"""The ledger obeys the knowledge base: full keys or candidate; closed reasons."""
from __future__ import annotations

from src.flow.evidence_ledger import (
    KIND_LEASE,
    KIND_TITLE_OPINION,
    STATUS_CLASSIFIED,
    STATUS_CONFIRMED,
    EvidenceEntry,
    EvidenceLedger,
)
from src.knowledge.loader import load_knowledge

K = load_knowledge()


def test_a_complete_identity_key_may_be_confirmed():
    led = EvidenceLedger()
    e = led.record_with_identity(
        "lease.pdf", KIND_LEASE, "lease",
        {"eog_lease_number": "0000000-000", "recording_book_page": "479.590"},
        K, identifier="0000000-000")
    assert e.status == STATUS_CONFIRMED and e.missing_identity_fields == []


def test_a_partial_key_stays_a_candidate_and_names_what_is_missing():
    led = EvidenceLedger()
    e = led.record_with_identity(
        "lease.pdf", KIND_LEASE, "lease",
        {"eog_lease_number": "0000000-000"},          # no recording
        K, identifier="0000000-000")
    assert e.status == STATUS_CLASSIFIED
    assert e.missing_identity_fields == ["recording_book_page"]
    # And a candidate never widens the derived allowlist.
    assert led.derive_allowlist("SOME UNIT")["leases"] == set()


def test_a_title_opinion_needs_abstract_acres_and_cert_date():
    led = EvidenceLedger()
    partial = led.record_with_identity(
        "to.pdf", KIND_TITLE_OPINION, "title_opinion",
        {"abstract": "227", "gross_acres": "141.5"}, K)
    assert partial.missing_identity_fields == ["cert_date"]
    full = led.record_with_identity(
        "to.pdf", KIND_TITLE_OPINION, "title_opinion",
        {"abstract": "227", "gross_acres": "141.5", "cert_date": "2008-10-18"},
        K, identifier="T-ANY")
    assert full.status == STATUS_CONFIRMED


def test_a_reason_outside_the_closed_vocabulary_is_a_conformance_problem():
    led = EvidenceLedger()
    led.add(EvidenceEntry("x.pdf", KIND_LEASE, reason="não achei, sei lá"))
    problems = led.conformance_problems(K)
    assert problems and "closed vocabulary" in problems[0]


def test_a_reason_from_the_vocabulary_conforms():
    led = EvidenceLedger()
    led.add(EvidenceEntry("x.pdf", KIND_LEASE, reason="doc_nao_localizado"))
    assert led.conformance_problems(K) == []


def test_confirming_on_an_incomplete_key_is_a_conformance_problem():
    led = EvidenceLedger()
    led.add(EvidenceEntry("x.pdf", KIND_LEASE, identifier="0000000-000",
                          status=STATUS_CONFIRMED,
                          missing_identity_fields=["recording_book_page"]))
    problems = led.conformance_problems(K)
    assert problems and "missing identity fields" in problems[0]


def test_entries_round_trip_through_the_case_file():
    led = EvidenceLedger()
    led.record_with_identity("to.pdf", KIND_TITLE_OPINION, "title_opinion",
                             {"abstract": "227"}, K)
    back = EvidenceLedger.from_dict(led.to_dict())
    assert back.entries[0].missing_identity_fields == ["gross_acres", "cert_date"]
    assert back.entries[0].identity == {"abstract": "227"}
