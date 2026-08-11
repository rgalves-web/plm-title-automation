"""S2 perimeter + D4 triage: the cheap filter, and never skipping blind."""
from __future__ import annotations

import pytest

from src.knowledge.perimeter import (
    Perimeter,
    SurveyScope,
    build_perimeter,
    cross_check,
    write_perimeter,
)
from src.knowledge.triage import (
    PEEK_NEEDED,
    READ,
    SKIP,
    TriageError,
    negative_knowledge,
    triage,
)

# Josh B's real perimeter: A-669, and A-319 only in Blocks 5 and 6.
JOSH_B = [SurveyScope("669"), SurveyScope("319", frozenset({"5", "6"}))]


# --- the abstract filter, including the block trap --------------------------

def test_the_perimeter_accepts_its_own_abstracts():
    p = Perimeter(unit="U", surveys=JOSH_B)
    assert p.covers("T-O ORIG W.S. SCARBOROUGH A-669 50AC.pdf")
    assert p.covers("T-O ORIG A-319 HILL CSL SURVEY BLKS 5 AND 6 318.3AC.pdf")


def test_the_same_abstract_in_another_block_is_outside():
    # A-319 Block 12 is a different place — this cost a real fetch.
    p = Perimeter(unit="U", surveys=JOSH_B)
    assert not p.covers("T0141729 A-319 Block 12 lease 2012 Newark E&P")
    assert p.outside_reason("A-319 Block 12 lease") == "fora_do_perimetro"


def test_other_abstracts_are_outside_with_a_vocabulary_reason():
    p = Perimeter(unit="U", surveys=JOSH_B)
    for name in ("T-O ORIG A-811 TEL CO SURVEY.pdf", "lease A-730 Donald",
                 "A-1100 E L Lehman", "A-257", "A-1148", "A-254 ETRR"):
        assert p.outside_reason(name) == "fora_do_perimetro", name


def test_a_document_naming_no_abstract_is_not_excluded_on_that_basis():
    # Silence is not evidence of being outside.
    p = Perimeter(unit="U", surveys=JOSH_B)
    assert p.outside_reason("Scan_0071 (3).pdf") is None


# --- the DPU is the authority; indexes are diffed at it ---------------------

def test_a_lease_the_authority_names_and_the_index_omits_is_a_fetch():
    p = Perimeter(unit="U", surveys=JOSH_B, authority="DPU Vol 611 Pg 526 p.3",
                  leases={"0220604-018": "Vol. 506, Pg. 386",
                          "0220604-021": "Vol. 557, Pg. 240"})
    found = cross_check(p, "XREF", {"0220604-018": "Vol. 506, Pg. 386"})
    assert len(found) == 1
    d = found[0]
    assert d.kind == "missing_from_index" and d.subject == "0220604-021"
    assert d.action == "fetch" and d.proof == "DPU Vol 611 Pg 526 p.3"


def test_a_recording_that_disagrees_is_a_confirm_not_a_fetch():
    # Josh B: DPU/T-O say 427.385; the seller's schedule says 427.685.
    p = Perimeter(unit="U", surveys=JOSH_B, leases={"0220604-002": "Vol. 427, Pg. 385"})
    found = cross_check(p, "Lease & Mineral Schedule",
                        {"0220604-002": "Vol. 427, Pg. 685"})
    assert len(found) == 1 and found[0].kind == "conflicting_recording"
    assert found[0].action == "confirm"
    assert found[0].reason == "confirmar_no_cartorio"
    assert "385" in found[0].authority_says and "685" in found[0].index_says


def test_building_the_perimeter_diffs_every_index_at_once():
    p = build_perimeter(
        unit="JOSH B UNIT", authority="DPU Vol 611 Pg 526 Exhibit A p.3",
        surveys=JOSH_B,
        exhibit_a_leases={"0220604-018": "506.386", "0220604-021": "557.240",
                          "0220604-023": "562.895", "0220750-017": "509.137"},
        indexes={"XREF": {}, "Schedule": {"0220604-018": "506.386"}})
    missing_from_xref = [d for d in p.divergences
                         if d.index_name == "XREF" and d.kind == "missing_from_index"]
    assert len(missing_from_xref) == 4          # the four Josh B leases
    assert p.abstract_labels() == ["A-669", "A-319 Blocks 5/6"]


def test_the_perimeter_is_written_to_the_case_never_to_a_package(tmp_path):
    from src.flow.deliverable_io import FrozenArtifactError
    p = Perimeter(unit="U", surveys=JOSH_B)
    assert write_perimeter(p, tmp_path).name == "perimeter.yaml"
    frozen = tmp_path / "U" / "SUBMISSION PLM"
    frozen.mkdir(parents=True)
    with pytest.raises(FrozenArtifactError):
        write_perimeter(p, frozen)


def test_the_perimeter_round_trips():
    p = build_perimeter("U", "DPU p.3", JOSH_B, {"L1": "1.2"},
                        indexes={"XREF": {}})
    back = Perimeter.from_dict(p.to_dict())
    assert back.abstract_labels() == p.abstract_labels()
    assert len(back.divergences) == 1


# --- D4: never skip blind ---------------------------------------------------

def _corpus(tmp_path):
    (tmp_path / "T-O ORIG A-730 OUTSIDE.pdf").write_bytes(b"outside-1")
    (tmp_path / "T-O ORIG A-669 INSIDE.pdf").write_bytes(b"inside-1")
    (tmp_path / "copy A-669.pdf").write_bytes(b"inside-1")      # byte-identical
    (tmp_path / "Thumbs.db").write_bytes(b"junk")
    return tmp_path


def test_without_a_peek_nothing_is_skipped_on_suspicion(tmp_path):
    p = Perimeter(unit="U", surveys=JOSH_B)
    result = triage(_corpus(tmp_path), perimeter=p, peek=None)
    pending = [e.path.name for e in result.unaccounted()]
    assert "T-O ORIG A-730 OUTSIDE.pdf" in pending      # proposed, not decided
    with pytest.raises(TriageError):
        # a skip without a look would be a blind skip — the guard catches it
        for e in result.entries:
            if e.disposition == PEEK_NEEDED:
                e.disposition, e.peeked = SKIP, False
        result.assert_no_blind_skip()


def test_a_peek_that_confirms_the_filename_lets_the_skip_stand(tmp_path):
    p = Perimeter(unit="U", surveys=JOSH_B)
    result = triage(_corpus(tmp_path), perimeter=p,
                    peek=lambda path: "TITLE OPINION ... A-730 Titus CSL ...")
    by_name = {e.path.name: e for e in result.entries}
    skipped = by_name["T-O ORIG A-730 OUTSIDE.pdf"]
    assert skipped.disposition == SKIP and skipped.peeked
    assert skipped.reason == "fora_do_perimetro"
    result.assert_no_blind_skip()


def test_a_peek_that_contradicts_the_filename_rescues_the_document(tmp_path):
    # The filename says A-730; the first page says A-669. Content wins.
    p = Perimeter(unit="U", surveys=JOSH_B)
    result = triage(_corpus(tmp_path), perimeter=p,
                    peek=lambda path: "TITLE OPINION ... W. Scarbrough A-669 ...")
    by_name = {e.path.name: e for e in result.entries}
    assert by_name["T-O ORIG A-730 OUTSIDE.pdf"].disposition == READ


def test_duplicates_and_non_documents_skip_without_a_look(tmp_path):
    p = Perimeter(unit="U", surveys=JOSH_B)
    result = triage(_corpus(tmp_path), perimeter=p, peek=lambda path: "A-730")
    by_name = {e.path.name: e for e in result.entries}
    assert by_name["Thumbs.db"].reason == "fora_do_tipo"
    # Exactly one of the two byte-identical files is the duplicate; WHICH one is
    # decided deterministically by sort order (case-insensitive on Windows), and
    # the pairing must point at the other.
    twins = [by_name["copy A-669.pdf"], by_name["T-O ORIG A-669 INSIDE.pdf"]]
    dups = [e for e in twins if e.reason == "duplicata"]
    assert len(dups) == 1
    dup = dups[0]
    assert dup.duplicate_of == next(e.path.name for e in twins if e is not dup)
    assert not dup.peeked
    result.assert_no_blind_skip()            # strong metadata, not a blind skip


def test_everything_is_counted_and_nothing_vanishes(tmp_path):
    p = Perimeter(unit="U", surveys=JOSH_B)
    result = triage(_corpus(tmp_path), perimeter=p, peek=lambda path: "A-730")
    counts = result.counts()
    assert counts["inventoried"] == 4
    assert counts["read"] + counts["skipped"] == counts["inventoried"]
    assert result.unaccounted() == []
    assert sum(result.skips_by_reason().values()) == counts["skipped"]


def test_skips_become_negative_knowledge_for_the_brief(tmp_path):
    p = Perimeter(unit="U", surveys=JOSH_B)
    result = triage(_corpus(tmp_path), perimeter=p, peek=lambda path: "A-730")
    notes = " ".join(negative_knowledge(result, p))
    assert "outside" in notes and "A-669" in notes
    assert "do not re-search" in notes
