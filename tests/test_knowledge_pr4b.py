"""PR-4b — the five rulings that came out of reading the first brief.

Each test names the real document or the real brief line that forced it.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from src.knowledge.classifier import _all_transmittal, _best_answer
from src.knowledge.fetch_brief import (ACTION_CONFIRM, ACTION_FETCH,
                                       ACTION_REQUEST, ACTION_RESCAN,
                                       ACTION_VERDICT, BriefItem,
                                       blocks_certification, validate_item)
from src.knowledge.lease_disposition import (STATUS_ILLEGIBLE,
                                             STATUS_NO_INSTRUMENT,
                                             STATUS_OF_RECORD,
                                             STATUS_UNIDENTIFIED, dispose)
from src.knowledge.loader import knowledge_root, load_knowledge


def _answer(category: str, confidence: float = 0.95) -> str:
    return json.dumps({"classified_as": category, "confidence": confidence,
                       "evidence": {"page": 1, "quote": "…"}})


# --- 1. the cover-page rule is general -------------------------------------

FIXTURE = (knowledge_root() / "fixtures" /
           "transmittal_cover_is_not_the_document" / "fixture.yaml")


def test_the_transmittal_fixture_exists_and_covers_more_than_one_type():
    doc = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))
    expected = {c["expect"] for c in doc["cases"]}
    # The bug was fixed on title opinions only. A fixture that only tests title
    # opinions would lock in exactly that mistake.
    assert len(expected - {"correspondence"}) >= 4, expected


@pytest.mark.parametrize("case", yaml.safe_load(
    FIXTURE.read_text(encoding="utf-8"))["cases"], ids=lambda c: c["name"])
def test_the_cover_page_never_names_the_document_for_any_type(case):
    answers = [_answer(page) for page in case["pages"]]
    assert _best_answer(answers)["classified_as"] == case["expect"]


def test_the_scan_keeps_going_only_while_every_page_is_a_cover_page():
    assert _all_transmittal([_answer("correspondence"), _answer("unplaced")])
    assert not _all_transmittal([_answer("correspondence"), _answer("lease_ogl")])


def test_a_letter_with_nothing_behind_it_is_not_promoted_to_an_instrument():
    # The thirteen "<LESSOR> LSE <no>.PDF" files really are letters. A rule that
    # manufactures an instrument to avoid saying "letter" is worse than the bug.
    out = _best_answer([_answer("correspondence", 1.0), _answer("correspondence")])
    assert out["classified_as"] == "correspondence"
    assert "_notes" not in out


# --- 2. absence is never inferred from unplaced ----------------------------

def _fetch(**kw) -> BriefItem:
    base = dict(id="F1", what="a lease", where=["the courthouse"],
                how="pull the recording", looks_like="an OGML",
                unlocks=["Lease Review!x"], already_searched=["read the folder"],
                action=ACTION_FETCH, source="county_clerk_records",
                effort="one lookup", origin="Exhibit A lists it")
    base.update(kw)
    return BriefItem(**base)


def test_a_fetch_item_that_leans_on_unplaced_fails_the_gate():
    item = _fetch(already_searched=["read the folder: FILE.PDF = unplaced"])
    problems = validate_item(item)
    assert any("infers ABSENCE" in p for p in problems), problems


def test_the_same_rule_applies_to_a_request():
    item = _fetch(action=ACTION_REQUEST, source="third_party_request",
                  how="e-mail the Seller; no cost",
                  origin="the folder held one unplaced document")
    assert any("infers ABSENCE" in p for p in validate_item(item))


def test_a_verdict_item_may_name_unplaced_freely():
    # The verdict item exists BECAUSE the file is unidentified; naming it is the
    # whole point.
    item = _fetch(action=ACTION_VERDICT, what="say what this file is",
                  already_searched=["FILE.PDF = unplaced"])
    assert not any("infers ABSENCE" in p for p in validate_item(item))


def test_a_clean_fetch_item_still_passes():
    assert not any("infers ABSENCE" in p for p in validate_item(_fetch()))


def test_an_unidentified_document_blocks_the_absence_verdict():
    k = load_knowledge()
    d = dispose("0220750-016", "Vol. 439, Pg. 540",
                [{"file": "PLAT.PDF", "classified_as": "unplaced",
                  "evidence": {}, "of_record": {}}], k)
    assert d.status == STATUS_UNIDENTIFIED
    assert "CANNOT be concluded" in d.note


def test_absence_is_stated_only_when_every_document_was_identified():
    k = load_knowledge()
    d = dispose("0220750-009", "Vol. 439, Pg. 442",
                [{"file": "LETTER.PDF", "classified_as": "correspondence",
                  "evidence": {}, "of_record": {}},
                 {"file": "TO.PDF", "classified_as": "title_opinion",
                  "evidence": {}, "of_record": {}}], k)
    assert d.status == STATUS_NO_INSTRUMENT
    assert "all identified" in d.note


# --- 3. blocking means blocks certification --------------------------------

def test_lease_review_does_not_block_certification():
    # PLM works the runsheet before the lease review, and a declared blank ships.
    assert not blocks_certification(["lease_review"])
    assert not blocks_certification(["potential_defects", "lease_review"])


def test_the_perimeter_and_verified_interest_do_block():
    assert blocks_certification(["perimeter"])
    assert blocks_certification(["ownership_wells"])
    assert blocks_certification(["lease_review", "ownership_report"])


# --- 5. illegible is its own disposition -----------------------------------

def test_an_illegible_instrument_is_a_rescan_not_a_fetch():
    k = load_knowledge()
    d = dispose("0221055-002", "Vol. 455, Pg. 603",
                [{"file": "LEASE.TIF", "classified_as": "unplaced",
                  "notes": ["the page is illegible"],
                  "evidence": {}, "of_record": {}}], k)
    assert d.status == STATUS_ILLEGIBLE
    assert "not a courthouse trip" in d.note


def test_a_legible_instrument_is_never_called_illegible():
    k = load_knowledge()
    d = dispose("0221055-002", "Vol. 455, Pg. 603",
                [{"file": "LEASE - REC.TIF", "classified_as": "lease_ogl",
                  "evidence": {"page": 1, "quote": "PAID-UP OIL, GAS AND MINERAL "
                                                   "LEASE"},
                  "of_record": {"status": "recorded"}}], k)
    assert d.status == STATUS_OF_RECORD


def test_rescan_is_a_real_action_the_validator_accepts():
    item = _fetch(action=ACTION_RESCAN, source="drive_plm",
                  how="open the TIF by hand")
    assert not any("unknown action" in p for p in validate_item(item))
