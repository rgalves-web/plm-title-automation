"""Turn a validation report into a human review queue + per-cell chain of proof.

Only cells that need human eyes reach the queue: an anchored value to confirm, a
named unverifiable to acknowledge, or (should it ever occur) a mismatch. Cells
the source-truth gate confirmed outright, or proved by rule, are trusted and do
not interrupt the reviewer. Pure functions over the engine's report — no I/O,
no engine changes.
"""
from __future__ import annotations

from typing import Any

# The outcomes that reach a human. Imported from the engine so the vocabulary
# stays single-sourced.
from src.dd.source_truth_check import (
    ANCHORED_VERIFIED,
    CONFIRMED_TRACT_LEVEL,
    MISMATCH,
    SEMANTICALLY_CHECKED,
    UNVERIFIABLE,
)

# Outcomes that warrant a verdict, most-urgent first.
_REVIEW_OUTCOMES = (MISMATCH, ANCHORED_VERIFIED, SEMANTICALLY_CHECKED,
                    CONFIRMED_TRACT_LEVEL, UNVERIFIABLE)
_URGENCY = {o: i for i, o in enumerate(_REVIEW_OUTCOMES)}

# How each outcome reads to the reviewer.
_LABEL = {
    MISMATCH: "MISMATCH",
    ANCHORED_VERIFIED: "NEEDS EYES",
    SEMANTICALLY_CHECKED: "NEEDS EYES",
    CONFIRMED_TRACT_LEVEL: "NEEDS EYES",
    UNVERIFIABLE: "UNVERIFIABLE",
}


def _finding_key(f: Any) -> str:
    return f"{getattr(f, 'sheet', '')}!{getattr(f, 'cell', '')}"


def review_items_from_report(report: Any) -> list[dict[str, Any]]:
    """The review queue: one row per cell that needs a human verdict.

    A blank/unverifiable carries its named reason; an anchored value carries the
    document it was matched against. CONFIRMED and by-rule cells are omitted —
    the reviewer only sees what the machine could not settle alone."""
    truth = getattr(report, "truth", None)
    if truth is None:
        return []
    items: list[dict[str, Any]] = []
    for f in getattr(truth, "findings", []):
        outcome = getattr(f, "outcome", "")
        if outcome not in _URGENCY:
            continue
        items.append({
            "tab": getattr(f, "sheet", ""),
            "cell": getattr(f, "cell", ""),
            "field": getattr(f, "field_name", ""),
            "value": _display(getattr(f, "workbook_value", "")),
            "outcome": outcome,
            "label": _LABEL.get(outcome, outcome),
            "source_file": getattr(f, "source_file", ""),
            "source_page": getattr(f, "source_page", ""),
            "detail": getattr(f, "detail", ""),
        })
    items.sort(key=lambda it: (_URGENCY.get(it["outcome"], 99), it["tab"], it["cell"]))
    return items


def trace_for_cell(report: Any, tab: str, cell: str,
                   verdicts: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """The full chain of proof for one cell: value, source document + page, the
    method that settled (or failed to settle) it, and the math when computed.
    Returns None if the cell is not in the report."""
    truth = getattr(report, "truth", None)
    if truth is None:
        return None
    for f in getattr(truth, "findings", []):
        if getattr(f, "sheet", "") == tab and getattr(f, "cell", "") == cell:
            outcome = getattr(f, "outcome", "")
            key = f"{tab}!{cell}"
            recorded = (verdicts or {}).get(key)
            return {
                "tab": tab, "cell": cell,
                "field": getattr(f, "field_name", ""),
                "value": _display(getattr(f, "workbook_value", "")),
                "source_file": getattr(f, "source_file", ""),
                "source_page": getattr(f, "source_page", ""),
                "method": outcome,
                "label": _LABEL.get(outcome, outcome),
                "detail": getattr(f, "detail", ""),
                "needs_verdict": outcome in (MISMATCH, ANCHORED_VERIFIED,
                                             SEMANTICALLY_CHECKED, CONFIRMED_TRACT_LEVEL),
                "recorded_verdict": recorded,
            }
    return None


def review_summary(report: Any) -> dict[str, int]:
    truth = getattr(report, "truth", None)
    if truth is None:
        return {"needs_eyes": 0, "unverifiable": 0, "mismatch": 0}
    items = review_items_from_report(report)
    return {
        "needs_eyes": sum(1 for it in items if it["label"] == "NEEDS EYES"),
        "unverifiable": sum(1 for it in items if it["label"] == "UNVERIFIABLE"),
        "mismatch": sum(1 for it in items if it["label"] == "MISMATCH"),
    }


def _display(value: Any) -> str:
    if value is None or str(value).strip() == "":
        return "—"
    return str(value)
