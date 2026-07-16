"""Resolve spreadsheet columns by HEADER NAME, and fail loudly when one is gone.

Every client reference workbook (XREF, Well List, Lease/Mineral Schedule) is a
periodic export, and its shape drifts: columns get renamed, reordered, dropped,
duplicated, and sheets get renamed. Reading them by hardcoded position is what
turns that drift into silent, confident nonsense. This bit us four times in one
session, and not one of them raised an error:

  * XREF "UNIT LEVEL NAME" (column AA / index 26) disappeared — row[26] threw
    only by luck of the row being short; a longer row would have read whatever
    sat there.
  * Well List "UNIT NAME" moved from index 28 to 23 — row[28] read "WELL #",
    matched no wells, and the unit silently ended up with no represented
    interest, a zero gross-acre denominator and WI "NOT_COMPUTED".
  * The Well List's "Wells" sheet was renamed to "Sheet1" — KeyError.
  * "RECORD TYPE" appears TWICE (the lease's type and the contract's); taking
    the first match classified every contract by its lease type.

The rule: resolve by name, fail with a message naming the column and the header
we actually saw. A loud failure costs minutes; a silent misread ships.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Sequence


class TabularSourceError(RuntimeError):
    """An expected column or sheet is missing/ambiguous in a client workbook."""


def normalize_header(values: Iterable[Any]) -> list[str]:
    return [str(v).strip().upper() if v is not None else "" for v in values]


@dataclass
class ColumnSpec:
    """One column to resolve.

    field:    the key the caller wants it under.
    names:    accepted header spellings, best first.
    after:    resolve the first match occurring AFTER this already-resolved
              field's column — for headers that legitimately repeat (the XREF
              prints "RECORD TYPE" once for the lease and once for the contract).
    required: when False, a missing column resolves to None instead of raising.
    """
    field: str
    names: Sequence[str]
    after: str | None = None
    required: bool = True


def resolve_header_columns(
    header: Iterable[Any],
    specs: Sequence[ColumnSpec],
    source: str = "workbook",
) -> dict[str, int]:
    """field -> column index. Raises TabularSourceError naming what is missing.

    Specs are resolved in order, so a spec may depend on an earlier one via
    `after`.
    """
    normalized = normalize_header(header)
    resolved: dict[str, int] = {}
    missing: list[str] = []

    for spec in specs:
        positions: list[int] = []
        for name in spec.names:
            positions = [i for i, h in enumerate(normalized) if h == name.strip().upper()]
            if positions:
                break
        if spec.after is not None and spec.after in resolved:
            later = [i for i in positions if i > resolved[spec.after]]
            positions = later or []
        if not positions:
            if spec.required:
                missing.append(f"{spec.field} (looked for {list(spec.names)}"
                               + (f" after {spec.after!r}" if spec.after else "") + ")")
            continue
        resolved[spec.field] = positions[0]

    if missing:
        raise TabularSourceError(
            f"{source}: expected column(s) not found: {'; '.join(missing)}. "
            f"Header actually seen: {[h for h in normalized if h]}. "
            "The export's shape changed — update the column spec rather than "
            "reading by position."
        )
    return resolved


def resolve_sheet(workbook, specs: Sequence[ColumnSpec], preferred: str | None = None,
                  exclude: Sequence[str] = (), source: str = "workbook"):
    """The worksheet whose HEADER satisfies *specs*, not whose name matches.

    Exports rename tabs ("Wells" -> "Sheet1"); matching on content survives that.
    `exclude` drops sheets by name substring — "Wells Removed" holds out-of-scope
    wells and must never be picked up as the well list.
    """
    candidates = [preferred] if preferred and preferred in workbook.sheetnames else []
    candidates += [s for s in workbook.sheetnames if s != preferred]
    excluded = tuple(x.casefold() for x in exclude)
    tried: list[str] = []
    for name in candidates:
        if any(x in name.casefold() for x in excluded):
            continue
        try:
            header = next(workbook[name].iter_rows(min_row=1, max_row=1, values_only=True))
        except StopIteration:
            continue
        tried.append(name)
        try:
            resolve_header_columns(header, specs, source=f"{source}:{name}")
        except TabularSourceError:
            continue
        return workbook[name]
    raise TabularSourceError(
        f"{source}: no sheet has the expected columns "
        f"({[s.field for s in specs if s.required]}). Sheets tried: {tried}; "
        f"all sheets: {workbook.sheetnames}.")


def read_rows(worksheet, columns: dict[str, int], min_row: int = 2) -> list[dict[str, Any]]:
    """Rows as {field: value} dicts using an already-resolved column map."""
    out: list[dict[str, Any]] = []
    for row in worksheet.iter_rows(min_row=min_row, values_only=True):
        if not row:
            continue
        out.append({field: (row[pos] if pos < len(row) else None)
                    for field, pos in columns.items()})
    return out
