"""Template structure baseline, the skeleton, and the provenance WHITELIST gate.

The PR-8 gate was a blacklist: six marker strings. External verification of the
artefact it approved found 759 cells it had no opinion about — "Dorothy Holder
Roberts", thirty repetitions of "Top of Bone Spring", a landman signature from
another job, a JOA effective date from the sample unit. None of those strings
was on the list, which is the permanent condition of every blacklist: it knows
only the leaks somebody already caught.

The whitelist inverts the burden of proof (CLAUDE.md invariant 25). A non-empty
cell in a deliverable is legitimate in exactly two ways:

  STRUCTURE — the pair (sheet, cell) is declared in
  `knowledge/templates/ddr_template_structure.yaml`, with the value the pristine
  template prints there: headers, labels, the Disclaimer text.

  PROVENANCE — the value has an entry in the artefact's own `DD_Audit_Trail`.

Anything else fails. The marker scrub may stay as defence; it is never again
the criterion.

The skeleton makes the gate cheap to satisfy: the artefact is BORN as template
minus sample (strip at origin), so the only way a cell becomes non-empty is a
recorded write. Scrubbing at the end — the PR-8 approach — meant every cell the
scrub did not recognise shipped.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import openpyxl

from src.knowledge.clean_output import (AUDIT_TRAIL_SHEET, CleanFinding,
                                        CleanReport)

STRUCTURE_YAML = Path("knowledge/templates/ddr_template_structure.yaml")

# Which cells of the pristine template are STRUCTURE, per sheet. Everything
# else non-empty in the template is the sample unit and is stripped. The rules
# were written by reading the template cell by cell (PR-9 item 2); the yaml
# they produce carries per-sheet counts for human review.
#   rows:        every non-empty cell in these rows
#   col_a_except: every non-empty column-A cell except the listed coordinates
#   all:         every non-empty cell (fixed text, e.g. the Disclaimer)
STRUCTURE_RULES: dict[str, dict[str, Any]] = {
    "Summary": {"labels_in_col_a": True},
    "Ownership - Worksheet": {"rows": [4, 7]},
    "Ownership - Wells": {"rows": [2]},
    "Lease Review": {"rows": [1]},
    "Agreements": {"labels_in_col_a": True},
    "Unit and Pooling Agreements": {"labels_in_col_a": True},
    "Runsheet": {"rows": [2]},
    "PLM Title Review": {"labels_in_col_a": True},
    "Disclaimer": {"all": True},
}

# On the label sheets, column A is structure when the cell is a LABEL (ends
# with a colon) or one of the template's fixed headings. A column-A cell that
# names a unit — "*** 3-11 A 601H, …", the block title of the sample's second
# JOA at A22 — is data, and the first draft of these rules blessed it. The
# validator caught that; the principle replaced the coordinate list.
FIXED_HEADINGS = {"Due Diligence Report", "JOA", "Unit/Pooling Agreement",
                  "PLM Title Review", "Title Opinion Summary"}

# The sample unit's own vocabulary, used ONLY to validate the baseline (item 2
# acceptance: no sample value may be classified as structure) — never as the
# shipping criterion.
SAMPLE_VOCABULARY = (
    "***", "Reeves", "Forest Oil", "A.E. Carroll", "636.13", "636.16",
    "Section **", "Bone Spring", "Wolfcamp", "Dorothy Holder Roberts",
    "Willard Kath", "Two Georges", "Phantom", "0.9896248", "Ma Chona Adaya",
    "Charlene R. Julian", "Stubbeman", "3-11",
)


class StructureError(AssertionError):
    """A sample value was about to be blessed as template structure."""


def introspect_template(template: str | Path) -> dict[str, Any]:
    """One pass over the pristine template -> the structure baseline.

    Runs AFTER the sample tabs are dropped and the Ownership tab is renamed, so
    the baseline keys the names the deliverable will actually have."""
    from src.knowledge.kit_builder import _prepare_workbook

    wb = openpyxl.load_workbook(template, data_only=True)
    try:
        _prepare_workbook(wb)
        sheets: dict[str, dict[str, str]] = {}
        counts: dict[str, dict[str, int]] = {}
        for name in wb.sheetnames:
            rules = STRUCTURE_RULES.get(name)
            if rules is None:
                raise StructureError(
                    f"no structure rule for sheet {name!r} — an unruled sheet "
                    f"would ship whatever the template carries")
            ws = wb[name]
            structure: dict[str, str] = {}
            total = 0
            for row in ws.iter_rows():
                for cell in row:
                    if cell.value is None:
                        continue
                    total += 1
                    if _is_structure(cell, rules):
                        structure[cell.coordinate] = str(cell.value)
            sheets[name] = structure
            counts[name] = {"structure": len(structure),
                            "sample_stripped": total - len(structure)}
        _validate_no_sample_in_structure(sheets)
        return {"template": Path(template).name, "sheets": sheets,
                "counts": counts}
    finally:
        wb.close()


def _is_structure(cell, rules: dict[str, Any]) -> bool:
    if rules.get("all"):
        return True
    if cell.row in (rules.get("rows") or []):
        return True
    if rules.get("labels_in_col_a") and cell.column_letter == "A":
        text = " ".join(str(cell.value).split())
        return text.endswith(":") or text in FIXED_HEADINGS
    return False


def _validate_no_sample_in_structure(sheets: dict[str, dict[str, str]]) -> None:
    """Item 2 acceptance: the baseline blesses no sample value."""
    offenders = []
    for sheet, cells in sheets.items():
        for coord, value in cells.items():
            if any(marker.lower() in value.lower()
                   for marker in SAMPLE_VOCABULARY):
                offenders.append(f"{sheet}!{coord}: {value[:60]!r}")
    if offenders:
        raise StructureError(
            "sample values classified as structure:\n  " + "\n  ".join(offenders))


def write_structure_yaml(template: str | Path,
                         out_path: str | Path = STRUCTURE_YAML) -> Path:
    import yaml

    data = introspect_template(template)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "# DDR template structure baseline — generated by ONE introspection of\n"
        "# the pristine template (PR-9 item 2). Every (sheet, cell) here is\n"
        "# STRUCTURE: headers, labels, the Disclaimer. Everything else the\n"
        "# template carries is the sample unit and is stripped at origin.\n"
        "# The counts below are the human-review annex.\n")
    out_path.write_text(header + yaml.safe_dump(data, sort_keys=True,
                                                allow_unicode=True),
                        encoding="utf-8")
    return out_path


def load_structure(path: str | Path = STRUCTURE_YAML) -> dict[str, dict[str, str]]:
    import yaml

    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return data["sheets"]


# ---------------------------------------------------------------------------
# Item 3 — the skeleton: strip at origin, not scrub at the end
# ---------------------------------------------------------------------------

def build_skeleton(template: str | Path,
                   structure: dict[str, dict[str, str]] | None = None):
    """Template minus sample. The workbook every write starts from."""
    from src.knowledge.kit_builder import _prepare_workbook

    structure = structure if structure is not None else load_structure()
    wb = openpyxl.load_workbook(template)
    _prepare_workbook(wb)
    for name in wb.sheetnames:
        keep = structure.get(name, {})
        for row in wb[name].iter_rows():
            for cell in row:
                if cell.value is None:
                    continue
                if cell.coordinate not in keep:
                    # openpyxl ignores cell(..., value=None); assign directly.
                    cell.value = None
    return wb


# ---------------------------------------------------------------------------
# Item 4 — the whitelist gate, over bytes re-read from disk
# ---------------------------------------------------------------------------

def check_provenance(path: str | Path,
                     structure: dict[str, dict[str, str]] | None = None,
                     max_report: int = 40) -> CleanReport:
    """Every non-empty cell is declared structure or carries provenance."""
    structure = structure if structure is not None else load_structure()
    report = CleanReport()
    path = Path(path)
    if not path.exists():
        report.findings.append(CleanFinding("FAIL", "missing_file", str(path),
                                            "the deliverable is not on disk"))
        return report

    wb = openpyxl.load_workbook(path, data_only=True)
    try:
        report.sheets = list(wb.sheetnames)
        trail: set[tuple[str, str]] = set()
        if AUDIT_TRAIL_SHEET in wb.sheetnames:
            for row in wb[AUDIT_TRAIL_SHEET].iter_rows(min_row=2,
                                                       values_only=True):
                if row and row[0] and row[1]:
                    trail.add((str(row[0]), str(row[1])))
        else:
            report.findings.append(CleanFinding(
                "FAIL", "no_audit_trail", AUDIT_TRAIL_SHEET,
                "no trail sheet — nothing in this artefact can prove itself"))

        orphans = 0
        for name in wb.sheetnames:
            if name == AUDIT_TRAIL_SHEET:
                continue                    # the trail IS the provenance
            keep = structure.get(name, {})
            for row in wb[name].iter_rows():
                for cell in row:
                    if cell.value is None:
                        continue
                    report.cells_checked += 1
                    expected = keep.get(cell.coordinate)
                    if expected is not None:
                        if _norm(cell.value) != _norm(expected):
                            report.findings.append(CleanFinding(
                                "FAIL", "structure_altered",
                                f"{name}!{cell.coordinate}",
                                f"declared structure carries a different value: "
                                f"{str(cell.value)[:60]!r}"))
                        continue
                    if (name, cell.coordinate) in trail:
                        continue
                    orphans += 1
                    if orphans <= max_report:
                        report.findings.append(CleanFinding(
                            "FAIL", "no_provenance", f"{name}!{cell.coordinate}",
                            f"neither structure nor trailed: "
                            f"{' '.join(str(cell.value).split())[:70]!r}"))
        if orphans > max_report:
            report.findings.append(CleanFinding(
                "FAIL", "no_provenance", "(more)",
                f"{orphans - max_report} further orphan cells not listed"))
        report.orphans = orphans
    finally:
        wb.close()
    return report


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value)).strip()


class ProvenanceError(AssertionError):
    """The artefact carries cells that nothing accounts for."""


def assert_provenance(path: str | Path, **kwargs: Any) -> CleanReport:
    report = check_provenance(path, **kwargs)
    if report.failed:
        lines = [str(f) for f in report.findings[:20]]
        raise ProvenanceError(
            f"{Path(path).name}: whitelist gate FAILED "
            f"({getattr(report, 'orphans', '?')} orphan cell(s)):\n  "
            + "\n  ".join(lines))
    return report


# ---------------------------------------------------------------------------
# Item 5 — the checklist is DERIVED from the bytes, never typed
# ---------------------------------------------------------------------------
#
# "Populated" is a fact about the artefact: at least one non-structure cell in
# the tab with a trail entry. The Summary row is stricter because PLM's own
# instruction names the fields ("Populate the rows covering Client-Date
# Submitted"): every named field must be filled, not just one. A checklist row
# that contradicts the artefact is a FAIL — the checklist asserts, and an
# assertion nobody derived is the PR-8 defect wearing a different tab.

SUMMARY_NAMED_FIELDS = ("Client:", "Acquisition:", "Operator(s):", "State:",
                        "Counties:", "DSU STR:", "PLM Landman:",
                        "Date Submitted:")


def tabs_populated(path: str | Path,
                   structure: dict[str, dict[str, str]] | None = None
                   ) -> dict[str, bool]:
    """Which tabs hold at least one trailed, non-structure value."""
    structure = structure if structure is not None else load_structure()
    wb = openpyxl.load_workbook(Path(path), data_only=True)
    try:
        trail: set[tuple[str, str]] = set()
        if AUDIT_TRAIL_SHEET in wb.sheetnames:
            for row in wb[AUDIT_TRAIL_SHEET].iter_rows(min_row=2,
                                                       values_only=True):
                if row and row[0] and row[1] and (len(row) < 4 or row[3]):
                    trail.add((str(row[0]), str(row[1])))
        out: dict[str, bool] = {}
        for name in wb.sheetnames:
            if name == AUDIT_TRAIL_SHEET:
                continue
            keep = structure.get(name, {})
            out[name] = any(
                cell.value is not None
                and cell.coordinate not in keep
                and (name, cell.coordinate) in trail
                for row in wb[name].iter_rows() for cell in row)

        # Summary: the instruction names the fields, so "populated" means the
        # named fields, each filled beside its label.
        if "Summary" in wb.sheetnames:
            ws = wb["Summary"]
            filled = 0
            for row in ws.iter_rows(min_row=1, max_row=20):
                for cell in row:
                    label = " ".join(str(cell.value or "").split())
                    if label in SUMMARY_NAMED_FIELDS:
                        neighbour = ws.cell(row=cell.row, column=cell.column + 1)
                        if neighbour.value is not None:
                            filled += 1
            out["Summary"] = filled == len(SUMMARY_NAMED_FIELDS)
    finally:
        wb.close()
    return out


def check_checklist_vs_artifact(checklist_path: str | Path,
                                ddr_path: str | Path,
                                row_to_tab: dict[int, str],
                                structure: dict[str, dict[str, str]] | None = None
                                ) -> CleanReport:
    """A checklist row that contradicts the artefact's own bytes is a FAIL."""
    populated = tabs_populated(ddr_path, structure)
    report = CleanReport()
    wb = openpyxl.load_workbook(Path(checklist_path), data_only=True)
    try:
        ws = wb[wb.sheetnames[0]]
        for row, tab in row_to_tab.items():
            answer = str(ws.cell(row=row, column=4).value or "").strip().lower()
            actual = populated.get(tab, False)
            report.cells_checked += 1
            if answer == "yes" and not actual:
                report.findings.append(CleanFinding(
                    "FAIL", "checklist_contradiction", f"row {row} ({tab})",
                    "says Yes; the artefact holds no trailed value in that tab"))
            elif answer == "no" and actual:
                report.findings.append(CleanFinding(
                    "FAIL", "checklist_contradiction", f"row {row} ({tab})",
                    "says No; the artefact holds trailed values in that tab"))
    finally:
        wb.close()
    return report
