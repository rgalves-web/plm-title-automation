"""PR-4: content-first classification, prose formulas, opinion scope.

Every test here encodes something a real document did, not something a spec
imagined. The comments name the document, because that is what makes a failing
test actionable a year from now.
"""
from __future__ import annotations

from fractions import Fraction
from pathlib import Path

import pytest

from src.knowledge.classifier import (FILENAME_ONLY_CEILING, Classification,
                                      _best_answer, filename_prior)
from src.knowledge.interest_formula import Blocking as FormulaBlocking
from src.knowledge.interest_formula import Parsed, parse_formula
from src.knowledge.title_opinion import (Blocking, _runsheet_recital,
                                         coverage_delta)


# --- prose interest formulas ----------------------------------------------

def test_the_compound_formula_from_the_traps_list_resolves_exactly():
    # CLAUDE.md "Known traps": this shape used to be dropped, not computed.
    r = parse_formula("62.5% x 7/8 less (62.5% x 50% x 5%) less (62.5% x 4.5%)")
    assert isinstance(r, Parsed)
    assert r.value == Fraction(161, 320)
    assert r.decimal == "0.50312500"
    assert [s for s, _, _ in r.terms] == [1, -1, -1]


def test_the_burden_factor_identity_from_the_flow_spec_closes():
    # Flow spec §2 rule 3: 0.875 - 0.066875 = 0.808125; 0.625 x that = 0.50507813
    burden = parse_formula("0.875 less 0.066875")
    assert isinstance(burden, Parsed) and burden.decimal == "0.80812500"
    assert parse_formula("62.5% x 80.8125%").decimal == "0.50507813"


def test_a_nested_group_is_a_formula_of_its_own():
    r = parse_formula("62.5% x (7/8 less 1/16)")
    assert isinstance(r, Parsed) and r.value == Fraction(65, 128)


@pytest.mark.parametrize("text,reason", [
    ("an undivided interest as set out above", "fator_ilegivel"),
    ("62.5% x 7/8 less (", "parenteses_desbalanceados"),
    ("", "formula_vazia"),
])
def test_an_unreadable_formula_blocks_and_never_returns_a_number(text, reason):
    # The failure this prevents is not a wrong number — it is silently adopting
    # an OLDER opinion because the newest one did not parse.
    r = parse_formula(text)
    assert isinstance(r, FormulaBlocking)
    assert r.reason == reason
    assert not hasattr(r, "value")


def test_a_zero_denominator_blocks_rather_than_raising():
    assert isinstance(parse_formula("7/0"), FormulaBlocking)


# --- title opinion scope ---------------------------------------------------

def test_the_bowen_a226_enlargement_is_flagged_from_the_descriptions_alone():
    # Original: 141.5 ac, A-227 only. First Supplemental: 262.5 ac, A-227 + A-226.
    original = ("141.5 acres, more or less, out of the Washington Edwards Survey "
                "No. 3, A-227, Montague County, Texas")
    supplemental = ("262.5 acres, more or less, out of the Washington Edwards "
                    "Survey No. 3, A-227; and the Washington Edwards Survey No. 2 "
                    "A-226, Montague County, Texas")
    d = coverage_delta(original, supplemental, "141.5", "262.5")
    assert d.changed
    assert d.abstracts_added == ["226"]
    assert not d.abstracts_removed
    assert "ENLARGED" in d.summary and "A-226" in d.summary


def test_an_unchanged_restatement_raises_nothing():
    text = "141.5 acres out of the Washington Edwards Survey No. 3, A-227"
    assert not coverage_delta(text, text, "141.5", "141.5").changed


def test_the_runsheet_recital_is_offered_as_a_candidate_not_adopted():
    # Bowen's First Supplemental has no certification sentence at all. The date
    # the delivered package used (10/18/2008) is the runsheet's through-date,
    # recited under DOCUMENTS EXAMINED — a human may adopt it; code may not.
    pages = ["cover page", "requirements",
             "B. Runsheet dated December 4, 2008, prepared by AED Group, LIC, "
             "tor FOG Re- sources, Inc., covering the Land from Sovereignty to "
             "October 18, 2008. Cc. Copies of the instruments"]
    candidate = _runsheet_recital(pages)
    assert candidate["value"] == "October 18, 2008"
    assert candidate["page"] == 3
    assert candidate["requires_human_verdict"] is True


def test_a_blocking_cert_date_carries_its_candidate_without_becoming_a_value():
    b = Blocking(subject="supp.pdf", reason="cert_date_nao_localizada",
                 candidate={"value": "October 18, 2008"})
    assert b.to_dict()["candidate"]["value"] == "October 18, 2008"
    assert "value" not in b.to_dict()


# --- classification --------------------------------------------------------

def test_the_filename_is_a_prior_with_a_hard_ceiling():
    # "T-O ORIG A-811 TEL CO SURVEY 3422 50AC.PDF" is a claim about a document,
    # and a claim never clears a risk floor on its own.
    assert filename_prior("T-O ORIG A-811 TEL CO SURVEY 3422 50AC.PDF") == "title_opinion"
    assert filename_prior("LEASE MEMO - REC.TIF") == "lease_memorandum"
    assert filename_prior("doc_007.pdf") == ""
    assert FILENAME_ONLY_CEILING < 0.5


def test_a_transmittal_cover_page_does_not_get_to_name_the_document():
    # Bowen's Original Title Opinion opens with "Dear Mr. Bynum: Enclosed please
    # find our Original Title Opinion". Reading page 1 alone filed an opinion as
    # correspondence, where it would never have reached the Ownership tabs.
    answers = ['{"classified_as": "correspondence", "confidence": 1.0}',
               '{"classified_as": "title_opinion", "confidence": 0.95}']
    best = _best_answer(answers)
    assert best["classified_as"] == "title_opinion"
    assert any("transmittal" in n for n in best["_notes"])


def test_pages_that_all_read_as_correspondence_stay_correspondence():
    answers = ['{"classified_as": "correspondence", "confidence": 0.9}',
               '{"classified_as": "unplaced", "confidence": 0.2}']
    assert _best_answer(answers)["classified_as"] == "correspondence"


def test_a_conflicting_filename_never_silently_overrides_content():
    c = Classification(file="LEASE.TIF", filename_prior="lease_ogl")
    from src.knowledge.classifier import _apply
    from src.knowledge.loader import load_knowledge
    out = _apply(c, {"classified_as": "lease_memorandum", "confidence": 0.95,
                     "evidence": {"page": 1, "quote": "Memorandum Of Oil, Gas and "
                                                      "Mineral Lease"}},
                 load_knowledge())
    assert out.classified_as == "lease_memorandum"
    assert out.conflicts and "filename suggested lease_ogl" in out.conflicts[0]


def test_a_classification_with_no_quote_cannot_clear_the_ceiling():
    from src.knowledge.classifier import _apply
    from src.knowledge.loader import load_knowledge
    out = _apply(Classification(file="x.pdf"),
                 {"classified_as": "lease_ogl", "confidence": 0.99, "evidence": {}},
                 load_knowledge())
    assert out.confidence <= FILENAME_ONLY_CEILING


def test_a_category_outside_the_closed_vocabulary_becomes_unplaced():
    from src.knowledge.classifier import _apply
    from src.knowledge.loader import load_knowledge
    out = _apply(Classification(file="x.pdf"),
                 {"classified_as": "mineral_deed_of_trust", "confidence": 0.99,
                  "evidence": {"page": 1, "quote": "whatever"}},
                 load_knowledge())
    assert out.classified_as == "unplaced"
    assert any("outside L1" in n for n in out.notes)


def test_a_filename_only_read_never_auto_confirms():
    from src.knowledge.classifier import verdict_queue
    from src.knowledge.loader import load_knowledge
    c = Classification(file="x.docx", read_method="filename_only",
                       classified_as="correspondence", confidence=0.99)
    assert verdict_queue([c], load_knowledge())["human"] == [c]
