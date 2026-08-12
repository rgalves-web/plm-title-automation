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
from src.knowledge.write_roots import record_write
from src.knowledge.clean_output import (AUDIT_TRAIL_SHEET, DELETE_TAB_PREFIX,
                                        PLACEHOLDER_MARKERS, assert_clean)

# The tabs a Josh B DDR must have, and only those. Taken from the template minus
# the sample unit's leftovers, which is exactly what the old pipeline did with
# `_drop_delete_tab`. Loading the template and typing over one tab ships the
# other nine as the sample unit.
EXPECTED_SHEETS = {
    "Summary", "Ownership - Worksheet", "Ownership - Wells", "Lease Review",
    "Agreements", "Unit and Pooling Agreements", "Runsheet",
    "PLM Title Review", "Disclaimer", AUDIT_TRAIL_SHEET,
}
# Tabs the template carries for its own sample unit. They are not ours.
SAMPLE_TABS = ("delete - ", "Ownership - 1H")
# The template's Ownership tab is named for the sample unit in some versions;
# PLM's instruction sheet names it "Ownership - Worksheet". Template-as-contract
# means renaming by introspection, never assuming either name.
OWNERSHIP_ALIASES = ("Ownership Report", "Ownership - Worksheet")


def _prepare_workbook(wb) -> list[str]:
    """Strip the template's sample unit before a single value is written.

    Returns what was removed, so the manifest can say it rather than the change
    being invisible."""
    removed: list[str] = []
    for name in list(wb.sheetnames):
        if any(name.lower().startswith(t.lower()) for t in SAMPLE_TABS):
            del wb[name]
            removed.append(name)
    for alias in OWNERSHIP_ALIASES:
        if alias in wb.sheetnames and alias != "Ownership - Worksheet":
            wb[alias].title = "Ownership - Worksheet"
            removed.append(f"{alias} -> Ownership - Worksheet")
    return removed


def _scrub_sample_cells(wb) -> int:
    """Blank every cell still carrying the template's sample unit.

    A cell we did not write and that names another operator's unit is not
    "leftover formatting" — it is a false statement about this unit."""
    scrubbed = 0
    for name in wb.sheetnames:
        for row in wb[name].iter_rows():
            for cell in row:
                if cell.value is None:
                    continue
                text = str(cell.value)
                if any(marker.lower() in text.lower()
                       for marker in PLACEHOLDER_MARKERS):
                    cell.value = None
                    scrubbed += 1
    return scrubbed


def write_audit_trail(wb, writes: list["CellWrite"]) -> int:
    """The evidence, IN the artefact. Bowen shipped with 1,099 entries; a DDR
    whose citations live only in a case file is not traceable on its own."""
    if AUDIT_TRAIL_SHEET in wb.sheetnames:
        del wb[AUDIT_TRAIL_SHEET]
    ws = wb.create_sheet(AUDIT_TRAIL_SHEET)
    ws.append(["SHEET", "CELL", "FIELD", "VALUE", "CITED TO", "REASON IF BLANK"])
    for c in writes:
        ws.append([c.sheet, f"{c.column}{c.row}", c.term,
                   str(c.value)[:500] if c.value else "",
                   c.citation, c.reason])
    return len(writes)

DPU_AUTHORITY = 'unit designation, Exhibit "A"'


def _norm_vp(value: Any) -> str:
    import re as _re
    digits = _re.findall(r"\d+", str(value or ""))
    return ".".join(digits[:2])


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


# "--" in a cell is not a blank: it asserts NOTHING EXISTS. The PR-8 artefact
# said "--" for Potential Defects while the gap-hunter held four blocking items.
# An absence token may be written only when the round COMPUTED the empty set,
# and the citation must say so.
ABSENCE_TOKENS = {"--", "-", "none", "n/a", "nenhum"}
DERIVED_EMPTY = "derived: computed empty set"


class AbsenceNotDerived(AssertionError):
    """An absence token was written without a computed empty set behind it."""


@dataclass
class CellWrite:
    sheet: str
    row: int
    column: str
    term: str
    value: Any
    citation: str = ""
    reason: str = ""

    def __post_init__(self) -> None:
        text = " ".join(str(self.value or "").split()).lower()
        if text in ABSENCE_TOKENS and DERIVED_EMPTY not in self.citation:
            raise AbsenceNotDerived(
                f"{self.sheet}!{self.column}{self.row}: {self.value!r} asserts "
                f"absence, and this round did not compute the empty set. An "
                f"unknown state never becomes a negative conclusion — leave the "
                f"cell blank with a reason, or derive the emptiness and cite it "
                f"({DERIVED_EMPTY!r}).")

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
              submitted: str,
              runsheet_entries: list[Any] | None = None,
              runsheet_basis: Any = None,
              extra_writers: list[Any] | None = None
              ) -> tuple[Path, list[CellWrite]]:
    """Fill Lease Review from the dispositions. Value+citation, or blank+reason."""
    out_path = Path(assert_not_frozen(out_path))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # The artefact is BORN as template-minus-sample (PR-9 item 3). Stripping at
    # origin, not scrubbing at the end: the only way a cell becomes non-empty
    # from here on is a recorded write.
    from src.knowledge.template_structure import build_skeleton
    wb = build_skeleton(template)
    ws = wb["Lease Review"]
    headers = _header_map(ws)
    writes: list[CellWrite] = []

    rows = [d for d in dispositions if d["status"] != "outside_perimeter"]
    rows.sort(key=lambda d: d["lease"])
    for i, d in enumerate(rows, start=2):
        id_col = _column_for(headers, "lease_id")
        if id_col:
            ws[f"{id_col}{i}"] = f"L{i - 1}  ({d['lease']})"
            writes.append(CellWrite(
                "Lease Review", i, id_col, "lease_id", f"L{i - 1}  ({d['lease']})",
                'unit designation, Exhibit "A" — row order of the Lease Review'))
        for term in ("lessor", "lessee", "instrument_date", "recording",
                     "legal_description", "term", "royalty", "shut_in",
                     "depth_limitation"):
            col = _column_for(headers, term)
            if not col:
                continue
            proved = (d.get("proved_terms") or {}).get(term)
            if term == "recording" and d.get("recording"):
                # Exhibit "A" is the AUTHORITY on which leases are in the unit
                # and at what recording (categories.yaml dpu.authority). An
                # extraction that scraped a volume/page off the page is not
                # allowed to overrule it: five rows carried the land
                # description's own deed reference as the lease's recording,
                # which is a wrong value where a blank would have been honest.
                extracted = str((proved or {}).get("value") or "")
                if extracted and _norm_vp(extracted) != _norm_vp(d["recording"]):
                    writes.append(CellWrite(
                        "Lease Review", i, col, term, d["recording"],
                        f'{DPU_AUTHORITY} (extraction read {extracted[:40]!r} — '
                        f'not adopted; Exhibit "A" is the authority)'))
                    ws[f"{col}{i}"] = d["recording"]
                    continue
                proved = {"value": d["recording"], "cited_to": DPU_AUTHORITY}
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

    if runsheet_entries:
        writes.extend(write_runsheet(wb, runsheet_entries, basis=runsheet_basis))

    # PR-10: the other tabs, written by the same contract — every writer takes
    # (wb, writes) and appends a CellWrite per touched cell, so the trail and
    # the whitelist gate see them exactly like Lease Review rows.
    for writer in (extra_writers or []):
        writer(wb, writes)

    summary = wb["Summary"]
    for row in summary.iter_rows(min_row=1, max_row=40):
        for cell in row:
            if str(cell.value or "").strip().lower().startswith("date submitted"):
                summary.cell(row=cell.row, column=cell.column + 1,
                             value=submitted)
                writes.append(CellWrite(
                    "Summary", cell.row,
                    summary.cell(row=cell.row, column=cell.column + 1)
                    .column_letter, "date_submitted", submitted,
                    "ship-time field, filled at packaging"))
    _scrub_sample_cells(wb)          # the blacklist stays as DEFENCE
    write_audit_trail(wb, writes)
    save_and_verify(wb, out_path)
    # The gates run on the BYTES, not on the workbook that produced them.
    # Whitelist first (invariant 25): structure or provenance, nothing else.
    from src.knowledge.template_structure import assert_provenance
    assert_provenance(out_path)
    assert_clean(out_path, expected_sheets=EXPECTED_SHEETS)
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
               ddr_path: Path, extras: dict[str, list[Path]] | None = None,
               corpus: Any = None
               ) -> tuple[dict[str, list[str]], list[dict[str, str]]]:
    """Assemble `1. Landman Submitted/`. COPIES only — nothing is moved.

    `corpus` is a CorpusIndex: sources are read straight out of the original
    zips (in place, read-only). Plain paths still work for files that exist."""

    def _copy(source: Any, dest: Path) -> bool:
        src_path = Path(str(source))
        if src_path.exists():
            shutil.copy2(src_path, dest)
            record_write(dest)
            return True
        if corpus is not None and corpus.exists(source):
            dest.write_bytes(corpus.read_bytes(source))
            record_write(dest)
            return True
        return False

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
        src = next((c["file"] for c in by_lease.get(d["lease"], [])
                    if c.get("classified_as") in ("lease_ogl", "lease_memorandum")
                    and (Path(c["file"]).exists()
                         or (corpus is not None and corpus.exists(c["file"])))),
                   None)
        lessor = ((d.get("proved_terms") or {}).get("lessor") or {}).get("value", "")
        if src is None:
            missing.append({"folder": "Leases", "lease": d["lease"],
                            "reason": d.get("note", "instrument not held")})
            continue
        dest = root / "Leases" / (_lease_filename(n, d.get("recording", ""), lessor)
                                  + Path(str(src)).suffix.lower())
        if _copy(src, dest):
            placed["Leases"].append(dest.name)
        else:
            missing.append({"folder": "Leases", "lease": d["lease"],
                            "reason": f"source unreadable: {Path(str(src)).name}"})

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
            # A source is a real path OR a member of the original zips read in
            # place through the corpus index. The bytes come first either way,
            # because dedup is by CONTENT: the same opinion filed in fourteen
            # lease folders ships once.
            name = Path(str(p)).name
            real = Path(str(p))
            if real.exists():
                blob = real.read_bytes()
            elif corpus is not None and corpus.exists(p):
                blob = corpus.read_bytes(p)
            else:
                missing.append({"folder": folder, "lease": "",
                                "reason": f"not held: {name}"})
                continue
            digest = hashlib.sha256(blob).hexdigest()
            if digest in seen:
                continue
            seen.add(digest)
            dest = target / name
            n = 1
            while dest.exists():
                n += 1
                dest = target / f"{Path(name).stem} ({n}){Path(name).suffix}"
            dest.write_bytes(blob)
            record_write(dest)
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


# ---------------------------------------------------------------------------
# Phase I - Checklist — without it the kit is not submissible, by PLM's own
# definition. A row is "Yes" only when the folder actually holds what the row
# describes; every "No" carries its pendência in Notes, because a No with no
# explanation is the same hole as a blank cell with no reason.
# ---------------------------------------------------------------------------

CHECKLIST_ROW_TO_FOLDER = {
    2: "Leases",
    3: None, 4: None, 5: None, 6: None, 7: None, 8: None, 9: None, 10: None,
    11: "Seller Files",
    12: "Title Documents",
    13: "Title Opinions",
    14: "Unit Designations",
    15: "Well Files",
}
# The PLM Report rows are about DDR TABS, not folders. A tab counts as done when
# the round converged for it — never because the file exists.
CHECKLIST_ROW_TO_TAB = {
    3: "Summary", 4: "Ownership - Worksheet", 5: "Ownership - Wells",
    6: "Lease Review", 7: "Agreements", 8: "Unit and Pooling Agreements",
    9: "Runsheet", 10: "PLM Title Review",
}


def fill_checklist(template: str | Path, out_path: str | Path, *,
                   placed: dict[str, list[str]], tabs_done: dict[str, bool],
                   notes: dict[int, str]) -> tuple[Path, dict[str, int]]:
    out_path = Path(assert_not_frozen(out_path))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.load_workbook(template)
    ws = wb[wb.sheetnames[0]]
    # The only checklist on disk is the one the operator filled by hand, so it
    # arrives carrying THEIR answers and THEIR numbers. Inheriting those is how
    # a generated checklist ends up asserting "94%" and "67 leases" about a kit
    # holding neither. Clear the answers before writing our own.
    for row in range(2, 16):
        # NOT ws.cell(..., value=None): openpyxl ignores a None value argument,
        # so that form reads as "clear this cell" and silently clears nothing.
        ws.cell(row=row, column=4).value = None
        ws.cell(row=row, column=5).value = None
    ws.cell(row=1, column=5).value = "Notes"

    tally = {"Yes": 0, "No": 0}
    for row in range(2, 16):
        folder = CHECKLIST_ROW_TO_FOLDER.get(row)
        tab = CHECKLIST_ROW_TO_TAB.get(row)
        if folder is not None:
            done = bool(placed.get(folder))
        elif tab is not None:
            done = bool(tabs_done.get(tab))
        else:
            done = False
        ws.cell(row=row, column=4, value="Yes" if done else "No")
        tally["Yes" if done else "No"] += 1
        note = notes.get(row, "")
        if note:
            ws.cell(row=row, column=5, value=note)
    save_and_verify(wb, out_path)
    return out_path, tally


# ---------------------------------------------------------------------------
# Runsheet tab — three dates, house style, one entry per instrument
# ---------------------------------------------------------------------------

RUNSHEET_HEADER_ROW = 2
RUNSHEET_FIRST_ROW = 4


def write_runsheet(wb, entries: list[Any], basis: Any = None) -> list[CellWrite]:
    """Write the Runsheet tab. Each entry is a drafted cell, not a fact."""
    ws = wb["Runsheet"]
    writes: list[CellWrite] = []
    if basis is not None:
        ws["A3"] = basis.statement
        writes.append(CellWrite("Runsheet", 3, "A", "basis", basis.statement,
                                "declared basis of the run"))
    cols = ["A", "B", "C", "D", "E", "F", "G", "H", "I"]
    for i, e in enumerate(entries, start=RUNSHEET_FIRST_ROW):
        values = [e.no, e.instrument, e.instrument_number, e.effective_date,
                  e.instrument_date, e.recorded_date, e.grantor, e.grantee,
                  e.acreage]
        for col, value in zip(cols, values):
            ws[f"{col}{i}"] = value
            # A runsheet cell with nothing in it is declared like any other
            # blank: the date the copy does not show is a fact about the copy.
            writes.append(CellWrite(
                "Runsheet", i, col, "runsheet", value, e.citation(),
                "" if value else "fato_inexistente_no_registro"))
        # The house style lives in the entry, not in a wall of pasted text.
        note = " ".join(x for x in (e.conveyance, e.reservation) if x)
        if note:
            ws[f"J{i}"] = note
            writes.append(CellWrite("Runsheet", i, "J", "entry", note,
                                    e.citation()))
    return writes
