"""S6 -> S7 -> S8 on the knowledge layer: ledger in, Phase I kit out.

Every cell written here is one of exactly two things, and the module has no
third branch:

  a VALUE with its citation (file + page, and for a borrowed form term, the
  sentence that authorises borrowing it); or
  a BLANK with a reason from the closed vocabulary.

That is the whole convergence criterion (flow spec §1, steps 14-15): the round
declares itself finished not when the sheet is full, but when every cell is
evidenced or declared and no blank is an orphan. "100% filled" with guessed
values is the only real failure.

The tree at the end is the PLM carbon copy (`PLM_PHASE1_SUBMISSION_SPEC`), built
in the replay namespace. Nothing here may touch a delivered package: every write
goes through `save_and_verify` / `assert_not_frozen`.
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import openpyxl

from src.flow.deliverable_io import assert_not_frozen, save_and_verify

# The Lease Review columns, in the template's own order. Read from the template
# header at write time; this is the mapping from our term names onto it.
TERM_TO_HEADER = {
    "lease_id": "TITLE OPINION",
    "type": "TYPE",
    "lessor": "LESSOR",
    "lessee": "LESSEE",
    "instrument_date": "EFFECTIVE",
    "recording": "RECORDING",
    "legal_description": "LEGAL DESCRIPTION",
    "term": "TERM OF",
    "royalty": "ROYALTY",
    "shut_in": "SHUT-IN",
    "depth_limitation": "DEPTH LIMITATIONS",
}


@dataclass
class CellWrite:
    sheet: str
    row: int
    column: str
    term: str
    value: Any
    citation: str = ""
    reason: str = ""

    @property
    def declared_blank(self) -> bool:
        return not self.value and bool(self.reason)

    def to_dict(self) -> dict[str, Any]:
        return {"sheet": self.sheet, "row": self.row, "column": self.column,
                "term": self.term, "value": self.value,
                "citation": self.citation, "reason": self.reason}


@dataclass
class BuildResult:
    ddr_path: Path | None = None
    cells: list[CellWrite] = field(default_factory=list)
    tree: dict[str, list[str]] = field(default_factory=dict)
    missing: list[dict[str, str]] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    @property
    def evidenced(self) -> int:
        return sum(1 for c in self.cells if c.value)

    @property
    def declared(self) -> int:
        return sum(1 for c in self.cells if c.declared_blank)

    @property
    def orphan(self) -> int:
        return sum(1 for c in self.cells if not c.value and not c.reason)

    def converged(self) -> bool:
        """The round says it is finished — or says why it is not."""
        return self.orphan == 0 and not self.problems


# ---------------------------------------------------------------------------
# S6 — write the DDR from the ledger
# ---------------------------------------------------------------------------

def _header_map(ws) -> dict[str, str]:
    out: dict[str, str] = {}
    for cell in next(ws.iter_rows(min_row=1, max_row=1)):
        text = " ".join(str(cell.value or "").split()).upper()
        if text:
            out[text] = cell.column_letter
    return out


def _column_for(headers: dict[str, str], term: str) -> str | None:
    want = TERM_TO_HEADER.get(term)
    if not want:
        return None
    for text, letter in headers.items():
        if text.startswith(want.upper()):
            return letter
    return None


def write_ddr(template: str | Path, out_path: str | Path,
              dispositions: list[dict[str, Any]], *, unit: str,
              submitted: str) -> tuple[Path, list[CellWrite]]:
    """Fill Lease Review from the dispositions. Value+citation, or blank+reason."""
    out_path = Path(assert_not_frozen(out_path))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.load_workbook(template)
    ws = wb["Lease Review"]
    headers = _header_map(ws)
    writes: list[CellWrite] = []

    rows = [d for d in dispositions if d["status"] != "outside_perimeter"]
    rows.sort(key=lambda d: d["lease"])
    for i, d in enumerate(rows, start=2):
        id_col = _column_for(headers, "lease_id")
        if id_col:
            ws[f"{id_col}{i}"] = f"L{i - 1}  ({d['lease']})"
        for term in ("lessor", "lessee", "instrument_date", "recording",
                     "legal_description", "term", "royalty", "shut_in",
                     "depth_limitation"):
            col = _column_for(headers, term)
            if not col:
                continue
            proved = (d.get("proved_terms") or {}).get(term)
            if proved and proved.get("value"):
                ws[f"{col}{i}"] = str(proved["value"])
                writes.append(CellWrite("Lease Review", i, col, term,
                                        proved["value"], proved.get("cited_to", "")))
            else:
                reason = (d.get("unproved_terms") or {}).get(term)
                pointer = (d.get("pointers") or {}).get(term)
                if pointer and not reason:
                    reason = "doc_nao_localizado"
                writes.append(CellWrite("Lease Review", i, col, term, "",
                                        "", reason or _status_reason(d)))

    summary = wb["Summary"]
    for row in summary.iter_rows(min_row=1, max_row=40):
        for cell in row:
            if str(cell.value or "").strip().lower().startswith("date submitted"):
                summary.cell(row=cell.row, column=cell.column + 1,
                             value=submitted)
    save_and_verify(wb, out_path)
    return out_path, writes


# ---------------------------------------------------------------------------
# S8 — the carbon-copy tree
# ---------------------------------------------------------------------------

SUBFOLDERS = ("Leases", "PLM Report", "Seller Files", "Title Documents",
              "Title Opinions", "Unit Designations", "Well Files")


def _lease_filename(n: int, recording: str, lessor: str) -> str:
    import re
    digits = re.findall(r"\d+", str(recording or ""))
    book_page = f"{digits[0]}.{digits[1]}" if len(digits) >= 2 else "unrecorded"
    who = " ".join(str(lessor or "Unknown").title().split())[:60]
    return f"L{n} - {book_page} - {who} OGL"


def build_tree(root: str | Path, *, unit_title: str,
               dispositions: list[dict[str, Any]],
               classifications: list[dict[str, Any]],
               ddr_path: Path, extras: dict[str, list[Path]] | None = None
               ) -> tuple[dict[str, list[str]], list[dict[str, str]]]:
    """Assemble `1. Landman Submitted/`. COPIES only — nothing is moved."""
    root = Path(assert_not_frozen(root)) / "1. Landman Submitted"
    if root.exists():
        shutil.rmtree(root)
    for name in SUBFOLDERS:
        (root / name).mkdir(parents=True, exist_ok=True)

    placed: dict[str, list[str]] = {name: [] for name in SUBFOLDERS}
    missing: list[dict[str, str]] = []

    by_lease: dict[str, list[dict[str, Any]]] = {}
    for c in classifications:
        by_lease.setdefault(str(c.get("lease")), []).append(c)

    n = 0
    for d in sorted(dispositions, key=lambda x: x["lease"]):
        if d["status"] == "outside_perimeter":
            continue
        n += 1
        src = next((Path(c["file"]) for c in by_lease.get(d["lease"], [])
                    if c.get("classified_as") in ("lease_ogl", "lease_memorandum")
                    and Path(c["file"]).exists()), None)
        lessor = ((d.get("proved_terms") or {}).get("lessor") or {}).get("value", "")
        if src is None:
            missing.append({"folder": "Leases", "lease": d["lease"],
                            "reason": d.get("note", "instrument not held")})
            continue
        dest = root / "Leases" / (_lease_filename(n, d.get("recording", ""), lessor)
                                  + src.suffix.lower())
        shutil.copy2(src, dest)
        placed["Leases"].append(dest.name)

    shutil.copy2(ddr_path, root / "PLM Report" / ddr_path.name)
    placed["PLM Report"].append(ddr_path.name)

    # Byte-identical copies of one document are ONE document. The corpus files
    # the same title opinion into a dozen lease folders; placing all twelve
    # would make the kit look complete and be wrong.
    import hashlib

    for folder, paths in (extras or {}).items():
        seen: set[str] = set()
        target = root / folder
        target.mkdir(parents=True, exist_ok=True)
        for p in paths:
            p = Path(p)
            if not p.exists():
                missing.append({"folder": folder, "lease": "",
                                "reason": f"not held: {p.name}"})
                continue
            digest = hashlib.sha256(p.read_bytes()).hexdigest()
            if digest in seen:
                continue
            seen.add(digest)
            dest = target / p.name
            n = 1
            while dest.exists():
                n += 1
                dest = target / f"{p.stem} ({n}){p.suffix}"
            shutil.copy2(p, dest)
            placed.setdefault(folder, []).append(dest.name)

    for name in SUBFOLDERS:
        if not placed.get(name):
            missing.append({"folder": name, "lease": "",
                            "reason": "no document of this kind is held"})
    return placed, missing


def write_manifest(root: str | Path, placed: dict[str, list[str]],
                   missing: list[dict[str, str]], result: "BuildResult") -> Path:
    root = Path(assert_not_frozen(root))
    lines = ["SUBMISSION MANIFEST", "=" * 60, ""]
    for folder in SUBFOLDERS:
        names = placed.get(folder, [])
        lines.append(f"{folder}/  ({len(names)})")
        lines += [f"    {x}" for x in sorted(names)[:200]]
        if not names:
            lines.append("    (empty — declared below)")
        lines.append("")
    lines += ["DECLARED GAPS", "-" * 60]
    for m in missing:
        lines.append(f"  {m['folder']}: {m.get('lease') or '-'} — {m['reason']}")
    lines += ["", "CONVERGENCE", "-" * 60,
              f"  cells evidenced : {result.evidenced}",
              f"  cells declared  : {result.declared}",
              f"  orphan blanks   : {result.orphan}",
              f"  converged       : {result.converged()}"]
    path = root / "SUBMISSION_MANIFEST.txt"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


# Every blank must carry a reason from the closed vocabulary (invariant 11).
# When a disposition has no per-term reason, its STATUS is the reason — an
# unidentified folder leaves blanks for a different cause than a missing lease,
# and the DDR reader is entitled to know which.
_STATUS_REASON = {
    "unidentified_documents_in_folder": "identidade_ambigua",
    "instrument_illegible": "doc_nao_localizado",
    "not_in_corpus": "doc_nao_localizado",
    "no_instrument_in_folder": "doc_nao_localizado",
    "terms_sourced_instrument_missing": "doc_nao_localizado",
    "memo_only": "doc_nao_localizado",
    "instrument_of_record": "doc_nao_localizado",
}


def _status_reason(d: dict[str, Any]) -> str:
    return _STATUS_REASON.get(str(d.get("status")), "doc_nao_localizado")


# A screen capture of a document is not the document. The operator's portal
# screenshots are working evidence — they belong in the ledger, and shipping one
# in place of an instrument makes a kit look complete while being empty.
SCREEN_CAPTURE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".gif"}


# Internal working paper never ships (flow spec §2 rule 5): it stays visible in
# the ledger and out of the client's kit. Being of record is NOT the test — a
# seller's ownership report is never recorded and belongs in Seller Files.
NEVER_SHIPS = frozenset({"correspondence", "unplaced", "reference_workbook"})


def is_shippable(path: Path, classification: dict[str, Any]) -> bool:
    if path.suffix.lower() in SCREEN_CAPTURE_SUFFIXES:
        return False
    return str(classification.get("classified_as")) not in NEVER_SHIPS
