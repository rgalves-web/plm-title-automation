"""Never regress below an approved baseline (Maxwell lessons R1).

The v5 Maxwell DDR is an APPROVED baseline: a human verified every value against
the source documents. Any later regeneration must be at least as complete. The
failure this guards against is silent and expensive — a pipeline change that
"fixes" one column while quietly emptying another looks like a clean run.

The rule is one-directional on purpose:

    every populated client-facing cell in the baseline must still be populated,
    and equal, in the candidate.

A candidate may populate MORE than the baseline (that is progress, not a
regression). It may never populate less, and it may never change a verified
value without that surfacing.

The audit/provenance layer is not compared — it is expected to differ every run.
Baselines are client material: they live on disk (data/reference/, gitignored)
and are never committed. Tests that need one skip when it is absent.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Provenance layers, not client-facing content — they legitimately differ.
_IGNORED_SHEETS = {"DD_Audit_Trail", "Pending Items"}

# Values that mean "intentionally empty" in the template.
_EMPTY_VALUES = {"", "-", "--", "—", "N/A"}

# Cells that are SUPPOSED to change between runs: the submission date and the
# review narrative (which reports the findings of the run that produced it).
# Comparing them would drown real regressions in guaranteed noise.
_VOLATILE_CELLS = {("Summary", "B9")} | {("Summary", f"B{r}") for r in (10, 11, 12, 13)}

# Relative tolerance absorbing a printed value's display rounding — a baseline
# that shows 22.3333 for 22.333333… is the same acreage, not a changed value.
_NUMERIC_REL_TOL = 1e-5


@dataclass
class CellRegression:
    sheet: str
    coordinate: str
    baseline: Any
    candidate: Any
    kind: str  # "lost" | "changed"

    def describe(self) -> str:
        if self.kind == "lost":
            return (f"{self.sheet} · {self.coordinate}: baseline has "
                    f"{str(self.baseline)[:40]!r}, regen is EMPTY — value lost.")
        return (f"{self.sheet} · {self.coordinate}: baseline {str(self.baseline)[:32]!r} "
                f"!= regen {str(self.candidate)[:32]!r} — verified value changed.")


@dataclass
class BaselineComparison:
    regressions: list[CellRegression] = field(default_factory=list)
    baseline_populated: int = 0
    candidate_populated: int = 0
    missing_sheets: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.regressions and not self.missing_sheets

    @property
    def lost(self) -> list[CellRegression]:
        return [r for r in self.regressions if r.kind == "lost"]

    @property
    def changed(self) -> list[CellRegression]:
        return [r for r in self.regressions if r.kind == "changed"]

    def summary(self) -> str:
        if self.passed:
            return (f"No regression: all {self.baseline_populated} populated baseline cell(s) "
                    f"present in the regen ({self.candidate_populated} populated).")
        parts = []
        if self.missing_sheets:
            parts.append(f"{len(self.missing_sheets)} sheet(s) missing: {', '.join(self.missing_sheets)}")
        if self.lost:
            parts.append(f"{len(self.lost)} value(s) lost")
        if self.changed:
            parts.append(f"{len(self.changed)} verified value(s) changed")
        return "REGRESSION vs approved baseline — " + "; ".join(parts) + "."


def _is_populated(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() not in _EMPTY_VALUES
    return True


def _normalize(value: Any) -> Any:
    """Compare what the reader sees: trim strings, unify numeric types."""
    if isinstance(value, str):
        text = value.strip()
        # A formula and its literal value are both "populated"; compare formulas
        # as text (openpyxl does not evaluate them).
        return text
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value)
    return value


def _normalize_text(text: str) -> str:
    """Collapse the differences that are not differences to a reader: case,
    surrounding space, and entity punctuation ("EOG Resources Inc" vs "… Inc.")."""
    cleaned = re.sub(r"[.,]+(?=\s|$)", "", text.casefold())
    return re.sub(r"\s+", " ", cleaned).strip()


def _numbers_equal(a: float, b: float) -> bool:
    scale = max(abs(a), abs(b), 1.0)
    return abs(a - b) <= _NUMERIC_REL_TOL * scale


def _values_equal(baseline: Any, candidate: Any) -> bool:
    b, c = _normalize(baseline), _normalize(candidate)
    if isinstance(b, float) and isinstance(c, float):
        return _numbers_equal(b, c)
    if isinstance(b, str) and isinstance(c, str):
        if _normalize_text(b) == _normalize_text(c):
            return True
        # "=1/4" vs "=2/8" are the same interest written two ways.
        bf, cf = _formula_value(b), _formula_value(c)
        return bf is not None and cf is not None and _numbers_equal(bf, cf)
    # A baseline literal 0.25 and a regen formula "=1/4" are not textually equal;
    # treat a formula as satisfying a numeric baseline only if it evaluates equal.
    if isinstance(b, float) and isinstance(c, str) and c.startswith("="):
        return _formula_value(c) is not None and _numbers_equal(b, _formula_value(c))
    if isinstance(c, float) and isinstance(b, str) and b.startswith("="):
        return _formula_value(b) is not None and _numbers_equal(c, _formula_value(b))
    return b == c


def _formula_value(text: str) -> float | None:
    """Evaluate the trivial '=N/D' fraction formulas the writer emits."""
    body = text[1:].strip()
    if "/" not in body:
        return None
    left, _, right = body.partition("/")
    try:
        denominator = float(right)
        return float(left) / denominator if denominator else None
    except ValueError:
        return None


def compare_to_baseline(candidate_workbook, baseline_workbook) -> BaselineComparison:
    """Assert the candidate is no less complete than the approved baseline."""
    result = BaselineComparison()
    for sheet_name in baseline_workbook.sheetnames:
        if sheet_name in _IGNORED_SHEETS:
            continue
        if sheet_name not in candidate_workbook.sheetnames:
            result.missing_sheets.append(sheet_name)
            continue
        baseline_sheet = baseline_workbook[sheet_name]
        candidate_sheet = candidate_workbook[sheet_name]
        for row in baseline_sheet.iter_rows():
            for cell in row:
                if not _is_populated(cell.value):
                    continue
                if (sheet_name, cell.coordinate) in _VOLATILE_CELLS:
                    continue  # changes every run by design
                result.baseline_populated += 1
                other = candidate_sheet[cell.coordinate].value
                if not _is_populated(other):
                    result.regressions.append(
                        CellRegression(sheet_name, cell.coordinate, cell.value, other, "lost"))
                elif not _values_equal(cell.value, other):
                    result.regressions.append(
                        CellRegression(sheet_name, cell.coordinate, cell.value, other, "changed"))
    for sheet_name in candidate_workbook.sheetnames:
        if sheet_name in _IGNORED_SHEETS:
            continue
        sheet = candidate_workbook[sheet_name]
        result.candidate_populated += sum(
            1 for row in sheet.iter_rows() for cell in row if _is_populated(cell.value))
    return result


def compare_files(candidate_path: str | Path, baseline_path: str | Path) -> BaselineComparison:
    import openpyxl

    candidate = openpyxl.load_workbook(candidate_path)
    baseline = openpyxl.load_workbook(baseline_path)
    try:
        return compare_to_baseline(candidate, baseline)
    finally:
        candidate.close()
        baseline.close()
