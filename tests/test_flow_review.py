"""Review queue + per-cell trace derived from a validation report."""
from __future__ import annotations

import types

from src.dd.source_truth_check import (
    ANCHORED_VERIFIED,
    CONFIRMED,
    MISMATCH,
    UNVERIFIABLE,
    VERIFIED_BY_RULE,
)
from src.flow.review import review_items_from_report, review_summary, trace_for_cell


def _f(sheet, cell, field, val, outcome, src="", page="", detail=""):
    return types.SimpleNamespace(
        sheet=sheet, cell=cell, field_name=field, workbook_value=val,
        source_value=val, outcome=outcome, source_file=src, source_page=page, detail=detail)


def _report(findings):
    return types.SimpleNamespace(truth=types.SimpleNamespace(findings=findings))


def test_only_cells_needing_eyes_reach_the_queue():
    rep = _report([
        _f("Ownership Report", "S14", "MI", "=1/8", CONFIRMED, "T-O.PDF", "p.2"),
        _f("Ownership Report", "U9", "Net acres", "=R*S", VERIFIED_BY_RULE, "(arithmetic)"),
        _f("Title Review", "B31", "OPR ref", "495/388", ANCHORED_VERIFIED, "IMG.png"),
        _f("Lease Review", "F52", "clause", None, UNVERIFIABLE, detail="document not located"),
    ])
    q = review_items_from_report(rep)
    keys = [(it["tab"], it["cell"], it["label"]) for it in q]
    assert ("Title Review", "B31", "NEEDS EYES") in keys
    assert ("Lease Review", "F52", "UNVERIFIABLE") in keys
    # Confirmed and by-rule cells never interrupt the reviewer.
    assert all(it["cell"] not in ("S14", "U9") for it in q)


def test_mismatch_sorts_first():
    rep = _report([
        _f("A", "1", "x", "v", UNVERIFIABLE),
        _f("A", "2", "y", "w", MISMATCH, "doc", "p.1", "value disagrees"),
        _f("A", "3", "z", "q", ANCHORED_VERIFIED),
    ])
    q = review_items_from_report(rep)
    assert q[0]["label"] == "MISMATCH"


def test_trace_returns_full_chain_for_a_cell():
    rep = _report([_f("Title Review", "B31", "OPR ref", "495/388",
                      ANCHORED_VERIFIED, "IMG_2204.png", "—", "matched by volume/page")])
    tr = trace_for_cell(rep, "Title Review", "B31")
    assert tr["value"] == "495/388"
    assert tr["source_file"] == "IMG_2204.png"
    assert tr["method"] == ANCHORED_VERIFIED
    assert tr["needs_verdict"] is True
    assert trace_for_cell(rep, "Title Review", "ZZ99") is None


def test_blank_cell_shows_a_dash_and_carries_reason():
    rep = _report([_f("Lease Review", "F52", "clause", None, UNVERIFIABLE,
                      detail="document not located")])
    it = review_items_from_report(rep)[0]
    assert it["value"] == "—"
    assert it["detail"] == "document not located"


def test_review_summary_counts():
    rep = _report([
        _f("A", "1", "x", "v", ANCHORED_VERIFIED),
        _f("A", "2", "y", "w", UNVERIFIABLE),
        _f("A", "3", "z", "q", CONFIRMED),
    ])
    s = review_summary(rep)
    assert s == {"needs_eyes": 1, "unverifiable": 1, "mismatch": 0}


def test_no_truth_report_is_empty():
    assert review_items_from_report(types.SimpleNamespace(truth=None)) == []
