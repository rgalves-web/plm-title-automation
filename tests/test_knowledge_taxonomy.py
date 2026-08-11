"""L1 — the taxonomy, and its acceptance: 100% of a real delivered corpus.

The acceptance for F2 is not "tests pass". It is that the ~10 categories cover
every file of a real unit's delivered corpus, counted, with whatever is left
over sitting in `unplaced` WITH a reason. Josh B is the richest fixture: 4 title
opinions (one per tract), 6 seller files, and a full lease and title-document
set. The corpus lives outside git, so the count runs when it is present and
reports an explicit SKIP when it is not.
"""
from __future__ import annotations

import os
from collections import Counter
from pathlib import Path

import openpyxl
import pytest
import yaml

from src.knowledge.loader import KnowledgeError, load_knowledge

K = load_knowledge()

# The delivered Josh B tree. Read-only: this test never writes.
JOSH_B = Path(os.environ.get(
    "JOSH_B_DELIVERED",
    r"C:\Users\Renato\PURPLE LAND MGMT\BKV122TX - Project Emirates"
    r"\JOSH B UNIT\1. Landman Submitted"))


# --- the shape of the taxonomy ---------------------------------------------

def test_the_taxonomy_loads_with_around_ten_categories():
    assert 10 <= len(K.taxonomy.categories) <= 16
    for name, cat in K.taxonomy.categories.items():
        assert cat.label and cat.relevance_test, name
        assert cat.risk_tier in ("high", "low"), name


def test_a_category_that_feeds_nothing_is_rejected(tmp_path):
    from src.knowledge.loader import Taxonomy
    bad = Taxonomy(version=1, categories={"ghost": {
        "label": "G", "feeds": [], "relevance_test": "?",
        "disposition_default": "read", "risk_tier": "low"}}, feedless_allowed=[])
    with pytest.raises(ValueError, match="feeds nothing"):
        bad.check_every_category_feeds_something()


def test_dispositions_may_feed_nothing_when_declared():
    # correspondence and unplaced are dispositions, not destinations.
    for name in K.taxonomy.feedless_allowed:
        assert K.category(name).feeds == []
    K.taxonomy.check_every_category_feeds_something()      # does not raise


def test_every_destination_a_category_feeds_exists():
    known = set(K.category_to_ddr.destinations)
    for name, cat in K.taxonomy.categories.items():
        assert set(cat.feeds) <= known, name


# --- template as contract, by introspection --------------------------------

def test_destinations_resolve_against_the_real_template_by_introspection():
    tpl = Path(r"C:\Users\Renato\PURPLE LAND MGMT\BKV122TX - Project Emirates"
               r"\DDR - Template (PLM).xlsx")
    if not tpl.exists():                                   # pragma: no cover
        pytest.skip("template not on this machine")
    tabs = openpyxl.load_workbook(tpl).sheetnames
    for dest in ("ownership_report", "ownership_wells", "lease_review",
                 "agreements", "unit_and_pooling_agreements", "runsheet",
                 "potential_defects"):
        assert K.category_to_ddr.resolve_tab(dest, tabs), dest


def test_a_tab_alias_from_another_template_version_also_resolves():
    # PLM template versions differ; the writer maps by what the job delivered.
    assert K.category_to_ddr.resolve_tab(
        "ownership_report", ["Ownership - Worksheet"]) == "Ownership - Worksheet"
    assert K.category_to_ddr.resolve_tab("ownership_report", ["Nothing"]) is None


# --- the supervisor's memorandum rule, as data -----------------------------

def test_a_memorandum_only_lease_is_both_a_source_and_a_missing_lease():
    dual = K.category("lease_memorandum").dual_disposition
    assert dual is not None
    assert dual.defect_label == "MISSING LEASE"
    assert "potential_defects" in K.category("lease_memorandum").feeds
    assert "lease_review" in K.category("lease_memorandum").feeds
    # What it cannot prove is a NAMED blank, never inferred from its silence.
    assert K.is_valid_reason(dual.reason_for_unstated_terms, "blank")


def test_the_runsheet_admits_only_of_record_instruments():
    assert K.category_to_ddr.destinations["runsheet"].admits_only_of_record
    assert K.category("correspondence").of_record is False
    assert K.category("correspondence").feeds == []        # never reaches a tab


# --- D5 risk tiers ----------------------------------------------------------

def test_everything_feeding_interest_math_demands_a_human_verdict():
    for name in ("title_opinion", "dpu", "lease_ogl", "lease_memorandum",
                 "assignment", "probate_heirship", "agreement"):
        assert K.needs_human_verdict(name), name
    for name in ("well_file", "reference_workbook"):
        assert not K.needs_human_verdict(name), name


def test_low_confidence_always_demands_a_verdict_whatever_the_tier():
    assert K.needs_human_verdict("well_file", confidence=0.4, floor=0.8)
    assert not K.needs_human_verdict("well_file", confidence=0.9, floor=0.8)


def test_an_unknown_category_demands_a_verdict():
    assert K.needs_human_verdict("something_new")
    with pytest.raises(KnowledgeError):
        K.category("something_new")


# --- ACCEPTANCE: 100% of the real Josh B corpus ----------------------------

def _classify_delivered(path: Path) -> str:
    """Which category a file in the DELIVERED tree belongs to.

    The delivered package is already sorted into folders by a human, so the
    folder is the label; this test measures whether the TAXONOMY has a home for
    every one of them — not whether a classifier can guess them. (Guessing from
    content is F4.)"""
    folder = path.parent.name
    grandparent = path.parent.parent.name
    if folder == "Leases":
        return "lease_ogl"
    if grandparent == "Title Opinions" or folder == "Title Opinions":
        return "title_opinion"
    if folder == "Title Documents":
        return "deed_release_lien"          # recorded instruments, book.page named
    if folder == "Unit Designations":
        return "dpu"
    if folder == "Well Files":
        return "well_file"
    if folder == "PLM Report":
        return "reference_workbook"         # the DDR itself
    if path.name.upper().startswith("PHASE I") and "CHECKLIST" in path.name.upper():
        return "submission_checklist"
    if folder == "Seller Files":
        name = path.name.upper()
        if "T-O " in name or "TITLE OPINION" in name:
            return "title_opinion"
        if "OWNERSHIP REPORT" in name:
            return "ownership_report"
        if "ASMT" in name or "ASSIGNMENT" in name or "CONVEYANCE" in name:
            return "assignment"
        return "correspondence"             # letters, responses
    return "unplaced"


@pytest.mark.skipif(not JOSH_B.exists(), reason="Josh B delivered corpus not on this machine")
def test_the_categories_cover_the_whole_josh_b_delivered_corpus():
    files = [p for p in JOSH_B.rglob("*") if p.is_file()
             and not p.name.startswith("~$")]
    assert files, "corpus is empty"

    counts: Counter[str] = Counter()
    unplaced: list[Path] = []
    for p in files:
        category = _classify_delivered(p)
        counts[category] += 1
        if category == "unplaced":
            unplaced.append(p)

    # Every category used must exist in the taxonomy.
    for name in counts:
        assert name in K.taxonomy.categories, f"{name} is not a declared category"

    print(f"\nJOSH B delivered corpus: {len(files)} files")
    for name, n in counts.most_common():
        print(f"  {n:4d}  {name}")
    if unplaced:
        print("  unplaced:")
        for p in unplaced:
            print(f"        {p.relative_to(JOSH_B)}")

    # 100% coverage: nothing may be unplaced without a reason, and here the
    # delivered tree is fully sorted, so nothing should be unplaced at all.
    assert not unplaced, (
        f"{len(unplaced)} delivered files have no category: "
        f"{[p.name for p in unplaced][:5]}")
    assert sum(counts.values()) == len(files)


@pytest.mark.skipif(not JOSH_B.exists(), reason="Josh B delivered corpus not on this machine")
def test_the_corpus_counts_are_reported_against_the_written_gabarito():
    """The gabarito (06/08 submission) states its own counts. The folder has
    kept growing since — this test REPORTS the difference instead of asserting
    a number that was true only on the day the package was built."""
    counts = Counter(_classify_delivered(p) for p in JOSH_B.rglob("*") if p.is_file())
    gabarito = {"lease_ogl": 53, "title_opinion": 4,
                "deed_release_lien": 19, "correspondence": 6}
    print("\nvs gabarito 06/08:")
    for name, expected in gabarito.items():
        print(f"  {name:20s} gabarito={expected:3d}  disco={counts.get(name, 0):3d}")
    assert counts["title_opinion"] >= 4         # one per tract, at minimum
    assert counts["lease_ogl"] >= 53            # never fewer than delivered
