"""Locate project reference files in the user's project folder.

Standing rule: the single authoritative copy of every project reference file
(XREF, Project Log, Well List, Lease/Mineral Schedule) lives in the user's
project folder — NOT in this repo. A copy inside the repo is stale by
construction: when the client issues a new export, the project folder gets it and
the repo copy silently keeps answering with last month's data. The pipeline
therefore reads reference files from the project root, always taking the NEWEST
version by the date printed in the filename.

    C:\\Users\\Renato\\PURPLE LAND MGMT\\BKV122TX - Project Emirates
      ├── Lease to Well and Contract XREF 06-16-2026 (1).xlsx   <- current XREF
      ├── BKV122TX - Project Log.xlsx
      ├── Well List - Updated 6.9.26 (1).xlsx
      ├── Lease & Mineral Schedule 6.9.26 (2).xlsx
      └── MAXWELL A UNIT/ ...                                    <- per-unit docs

Client data never enters the repo and never leaves the machine (invariant 7):
these files are READ IN PLACE.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

# The project root for Project Emirates (engagement BKV122TX).
DEFAULT_PROJECT_ROOT = Path(r"C:\Users\Renato\PURPLE LAND MGMT\BKV122TX - Project Emirates")

# Filenames date themselves inconsistently: "06-16-2026", "6.9.26", "2026_07_09".
_DATE_PATTERNS = (
    re.compile(r"(?P<m>\d{1,2})[-_.](?P<d>\d{1,2})[-_.](?P<y>\d{4})"),   # 06-16-2026
    re.compile(r"(?P<y>\d{4})[-_.](?P<m>\d{1,2})[-_.](?P<d>\d{1,2})"),   # 2026_07_09
    re.compile(r"(?P<m>\d{1,2})[-_.](?P<d>\d{1,2})[-_.](?P<y>\d{2})\b"),  # 6.9.26
)

# A "Copy of ..." duplicate is never preferred over the original.
_COPY_RE = re.compile(r"^\s*copy of\b", re.IGNORECASE)

REFERENCE_PATTERNS = {
    "xref": "*XREF*.xlsx",
    "project_log": "*Project Log*.xlsx",
    "well_list": "*Well List*.xlsx",
    "lease_mineral_schedule": "*Lease & Mineral Schedule*.xlsx",
    "ddr_template": "*DDR - Template*.xlsx",
}


def date_in_filename(name: str) -> date | None:
    """The date a reference file names itself with, if any."""
    for pattern in _DATE_PATTERNS:
        match = pattern.search(name)
        if not match:
            continue
        year = int(match.group("y"))
        if year < 100:
            year += 2000
        try:
            return date(year, int(match.group("m")), int(match.group("d")))
        except ValueError:
            continue
    return None


def _rank(path: Path) -> tuple:
    """Newest dated version wins; a dated file beats an undated one; an original
    beats a "Copy of"; mtime breaks any remaining tie."""
    parsed = date_in_filename(path.name)
    return (
        parsed is not None,
        parsed or date.min,
        not bool(_COPY_RE.match(path.name)),
        path.stat().st_mtime,
    )


def find_reference(kind: str, project_root: Path | str | None = None) -> Path | None:
    """The newest copy of a reference file in the project root.

    kind: one of REFERENCE_PATTERNS. Returns None when absent — callers surface
    that rather than falling back to a stale in-repo copy.
    """
    if kind not in REFERENCE_PATTERNS:
        raise ValueError(f"unknown reference kind {kind!r}; known: {sorted(REFERENCE_PATTERNS)}")
    root = Path(project_root or DEFAULT_PROJECT_ROOT)
    if not root.exists():
        return None
    candidates = [p for p in root.glob(REFERENCE_PATTERNS[kind]) if p.is_file()]
    return max(candidates, key=_rank) if candidates else None


def unit_folder(unit_name: str, project_root: Path | str | None = None) -> Path | None:
    """The per-unit document folder ("MAXWELL A UNIT") under the project root."""
    root = Path(project_root or DEFAULT_PROJECT_ROOT)
    if not root.exists():
        return None
    target = unit_name.strip().upper()
    for child in root.iterdir():
        if child.is_dir() and child.name.strip().upper() == target:
            return child
    return None


def describe_references(project_root: Path | str | None = None) -> dict[str, str | None]:
    """kind -> resolved filename (or None), for the audit trail."""
    return {kind: (path.name if path else None)
            for kind, path in ((k, find_reference(k, project_root)) for k in REFERENCE_PATTERNS)}
