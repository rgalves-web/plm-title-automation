"""Never overwrite a manually verified value (Maxwell lessons R2).

When a human opens the source PDFs, resolves an ambiguity the pipeline could not,
and writes the answer into the workbook, that answer outranks anything the
pipeline recomputes. The v5 baseline carries several: Hulme's MI corrected from
5/36 to 5/288, Marilyn J. Parker resolved to the Benoe Parker interest via the
opinion's own Requirement 20.B, the 0220344-022 royalty read off page 8.

Regeneration must CARRY THESE FORWARD rather than recompute them. If a
recomputation disagrees, that is worth a reviewer's attention — the pipeline may
now be right, or it may have re-introduced the very error the human fixed — so we
itemize the disagreement and keep the human's value. We never silently overwrite,
and we never silently discard the pipeline's finding either.

Protected cells are identified from the baseline's own DD_Audit_Trail: any row
whose Source Type contains "manual" (manual, manual_verified, manual_inherited,
merged+manual).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_AUDIT_SHEET = "DD_Audit_Trail"
_MANUAL_MARKER = "manual"

# DD_Audit_Trail column order as written by ddr_writer.
_COL_SHEET, _COL_LOCATION, _COL_SOURCE_TYPE, _COL_SOURCE_REF = 1, 2, 3, 4

_CELL_RE = re.compile(r"\b([A-Z]{1,3}[0-9]{1,7})\b")


@dataclass(frozen=True)
class ProtectedValue:
    sheet: str
    coordinate: str
    value: Any
    source_type: str
    source_reference: str = ""

    def describe(self) -> str:
        return (f"{self.sheet} · {self.coordinate} = {str(self.value)[:32]!r} "
                f"[{self.source_type}] {self.source_reference[:60]}")


@dataclass
class ProtectionResult:
    carried_forward: list[ProtectedValue] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """Carrying values forward is normal; only a DISAGREEMENT needs review."""
        return not self.conflicts


def _audit_locations(baseline_workbook) -> list[tuple[str, str, str, str]]:
    """(sheet, location_text, source_type, source_reference) for manual rows."""
    if _AUDIT_SHEET not in baseline_workbook.sheetnames:
        return []
    sheet = baseline_workbook[_AUDIT_SHEET]
    out: list[tuple[str, str, str, str]] = []
    for row in range(2, sheet.max_row + 1):
        source_type = sheet.cell(row, _COL_SOURCE_TYPE).value
        if not source_type or _MANUAL_MARKER not in str(source_type).lower():
            continue
        target_sheet = sheet.cell(row, _COL_SHEET).value
        location = sheet.cell(row, _COL_LOCATION).value
        if not target_sheet or not location:
            continue
        out.append((str(target_sheet), str(location), str(source_type),
                    str(sheet.cell(row, _COL_SOURCE_REF).value or "")))
    return out


def find_protected_values(baseline_workbook) -> list[ProtectedValue]:
    """Every manually verified cell in the baseline, resolved to a coordinate.

    An audit row's Location may name a single cell ("row 0220344-021 col S") or a
    region ("cols S/T Cox-tract rows"). Only rows that resolve to an explicit
    cell reference can be protected mechanically; the rest are returned by
    `unresolved_protected_locations` for a human to check, never guessed at.
    """
    protected: list[ProtectedValue] = []
    for target_sheet, location, source_type, source_ref in _audit_locations(baseline_workbook):
        if target_sheet not in baseline_workbook.sheetnames:
            continue
        for coordinate in _CELL_RE.findall(location.upper()):
            try:
                value = baseline_workbook[target_sheet][coordinate].value
            except (ValueError, KeyError):
                continue
            protected.append(ProtectedValue(target_sheet, coordinate, value,
                                            source_type, source_ref))
    return protected


def unresolved_protected_locations(baseline_workbook) -> list[str]:
    """Manual audit rows whose Location is a prose region, not a cell reference.
    These cannot be carried forward mechanically and must be checked by hand."""
    return [f"{sheet} · {location} [{source_type}] — {ref[:60]}"
            for sheet, location, source_type, ref in _audit_locations(baseline_workbook)
            if not _CELL_RE.findall(location.upper())]


def apply_protected_values(candidate_workbook, protected: list[ProtectedValue]) -> ProtectionResult:
    """Carry each protected value into the candidate, itemizing disagreements."""
    result = ProtectionResult()
    for item in protected:
        if item.sheet not in candidate_workbook.sheetnames:
            result.conflicts.append(
                f"{item.sheet} · {item.coordinate}: sheet missing from the regen — "
                f"manually verified value {str(item.value)[:32]!r} cannot be carried forward.")
            continue
        cell = candidate_workbook[item.sheet][item.coordinate]
        computed = cell.value
        if computed is not None and str(computed).strip() != str(item.value).strip():
            result.conflicts.append(
                f"{item.sheet} · {item.coordinate}: pipeline computed "
                f"{str(computed)[:32]!r} but the manually verified value is "
                f"{str(item.value)[:32]!r} [{item.source_type}] — keeping the verified "
                f"value; confirm against {item.source_reference[:60] or 'the source'}.")
        cell.value = item.value  # the human's value always wins
        result.carried_forward.append(item)
    return result
