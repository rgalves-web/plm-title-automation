"""Source-truth validation: does each cell match the document it cites?

The structural rules in ddr_validator verify FORM — an NRI in range, no orphan
cells, no foreign unit. They cannot tell you the workbook is WRONG: a royalty of
1/5 is structurally perfect and still false if the lease says 1/4. This module
re-opens the cited source and checks the value is actually stated there.

What "re-read fresh" means here, precisely
------------------------------------------
We re-read the DOCUMENT TEXT (deterministic tesseract OCR) and confirm the value
against it. We do NOT re-run the LLM extraction that produced the cell: a second
LLM pass is another opinion, not a check, and this project has already been bitten
by its non-determinism (the same Cox opinion extracted twice gave royalty_owners
25 and 0). Reading the text independently of the structured extraction is the
check that has teeth.

Three outcomes, and the discipline that keeps MISMATCH meaningful
----------------------------------------------------------------
  CONFIRMED    the value is stated in the source.
  MISMATCH     the source states a DIFFERENT value for the same field. Claimed
               ONLY when a comparable value is located and it differs.
  UNVERIFIABLE no source on disk, the "source" is not a document (manifest,
               dd_pipeline), the audit cite is too coarse to test, or the value
               could not be located in the text.

A value merely not found in OCR text is UNVERIFIABLE, never MISMATCH. OCR is
lossy and instruments paraphrase; calling that a mismatch would accuse the
workbook of being wrong on the strength of a bad scan. The same over-reach
turned an earlier leakage rule into 8,575 false failures.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from fractions import Fraction
from pathlib import Path
from typing import Any

from src.dd.unit_aggregation import parse_fraction_text
from src.utils import get_logger

logger = get_logger(__name__)

CONFIRMED = "CONFIRMED"
MISMATCH = "MISMATCH"
UNVERIFIABLE = "UNVERIFIABLE"

# Audit "sources" that are not documents — nothing to re-read.
_NON_DOCUMENT_SOURCES = {
    "manifest", "dd_pipeline", "aggregation_computed", "formula",
    "unit_aggregation.run_dd_aggregation", "supplemental search - clean result",
    "controlling certification date range", "Lease to Well XREF",
}

_EXCEL_EPOCH = date(1899, 12, 30)


@dataclass(frozen=True)
class TruthFinding:
    sheet: str
    cell: str
    field_name: str
    workbook_value: Any
    source_value: Any
    outcome: str
    source_file: str = ""
    source_page: str = ""
    detail: str = ""

    def describe(self) -> str:
        if self.outcome == MISMATCH:
            return (f"[MISMATCH] {self.sheet} · {self.cell} · {self.field_name}: "
                    f"workbook={str(self.workbook_value)[:40]!r} but "
                    f"{self.source_file}{(' ' + self.source_page) if self.source_page else ''} "
                    f"says {str(self.source_value)[:40]!r}")
        if self.outcome == CONFIRMED:
            return (f"[CONFIRMED] {self.sheet} · {self.cell} · {self.field_name} = "
                    f"{str(self.workbook_value)[:36]!r} in {self.source_file} {self.source_page}".rstrip())
        return (f"[UNVERIFIABLE] {self.sheet} · {self.cell} · {self.field_name}: "
                f"{self.detail}")


@dataclass
class SheetTruth:
    sheet: str
    confirmed: int = 0
    mismatched: int = 0
    unverifiable: int = 0

    @property
    def checked(self) -> int:
        return self.confirmed + self.mismatched + self.unverifiable


@dataclass
class TruthReport:
    findings: list[TruthFinding] = field(default_factory=list)
    per_sheet: dict[str, SheetTruth] = field(default_factory=dict)

    def add(self, finding: TruthFinding) -> None:
        self.findings.append(finding)
        sheet = self.per_sheet.setdefault(finding.sheet, SheetTruth(finding.sheet))
        if finding.outcome == CONFIRMED:
            sheet.confirmed += 1
        elif finding.outcome == MISMATCH:
            sheet.mismatched += 1
        else:
            sheet.unverifiable += 1

    @property
    def mismatches(self) -> list[TruthFinding]:
        return [f for f in self.findings if f.outcome == MISMATCH]

    @property
    def unverifiable(self) -> list[TruthFinding]:
        return [f for f in self.findings if f.outcome == UNVERIFIABLE]

    @property
    def confirmed(self) -> list[TruthFinding]:
        return [f for f in self.findings if f.outcome == CONFIRMED]

    @property
    def truthful(self) -> bool:
        """A DDR may ship only with zero contradicted values."""
        return not self.mismatches

    def summary(self) -> str:
        return (f"{len(self.confirmed)} confirmed, {len(self.mismatches)} MISMATCH, "
                f"{len(self.unverifiable)} unverifiable")


# ---------------------------------------------------------------------------
# Source resolution + text access
# ---------------------------------------------------------------------------

class SourceIndex:
    """Resolves an audit source reference to a file, and caches its text."""

    def __init__(self, search_roots: list[Path], ocr_fn=None) -> None:
        self.search_roots = [Path(r) for r in search_roots if r and Path(r).exists()]
        self._files: dict[str, Path] = {}
        self._text: dict[Path, str] = {}
        self._ocr_fn = ocr_fn
        for root in self.search_roots:
            for path in root.rglob("*"):
                if path.is_file() and path.suffix.lower() in {".pdf", ".tif", ".tiff", ".txt"}:
                    self._files.setdefault(_norm_key(path.stem), path)

    def resolve(self, reference: str | None) -> Path | None:
        """An audit source reference -> the file on disk, or None."""
        if not reference:
            return None
        first = str(reference).split(" + ")[0].strip()
        if first in _NON_DOCUMENT_SOURCES:
            return None
        stem = Path(first).stem
        key = _norm_key(stem)
        if key in self._files:
            return self._files[key]
        # A reference may carry a page cite or trailing prose ("T-O SUPP COX pp.5-6").
        trimmed = _norm_key(re.split(r"\bPP?\.", stem, maxsplit=1)[0])
        if trimmed and trimmed in self._files:
            return self._files[trimmed]
        for candidate_key, path in self._files.items():
            if trimmed and (trimmed in candidate_key or candidate_key in trimmed):
                return path
        return None

    def text(self, path: Path) -> str:
        if path not in self._text:
            if path.suffix.lower() == ".txt":
                self._text[path] = path.read_text(encoding="utf-8", errors="replace")
            else:
                ocr = self._ocr_fn or _default_ocr
                self._text[path] = ocr(path)
        return self._text[path]

    def page_text(self, path: Path, page: int | None) -> str:
        text = self.text(path)
        if page is None:
            return text
        pages = text.split("\f")
        return pages[page - 1] if 0 < page <= len(pages) else text


def _default_ocr(path: Path) -> str:
    from src.pdf_reader import extract_document
    return extract_document(path).full_text or ""


def _norm_key(text: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "", str(text).upper())


def normalize_for_match(text: Any) -> str:
    """Collapse the differences OCR invents: case, spacing, punctuation."""
    return re.sub(r"[^A-Z0-9]+", "", str(text).upper())


def states_value(source_text: str, value: Any) -> bool:
    """Is *value* stated in the source text? Punctuation/space-insensitive."""
    needle = normalize_for_match(value)
    return bool(needle) and needle in normalize_for_match(source_text)


# ---------------------------------------------------------------------------
# Computable cross-checks (these are where MISMATCH is meaningful)
# ---------------------------------------------------------------------------

def excel_serial_to_date(serial: Any) -> date | None:
    try:
        return _EXCEL_EPOCH + timedelta(days=int(float(serial)))
    except (TypeError, ValueError):
        return None


_MONTHS = ("january february march april may june july august september october "
           "november december").split()


def parse_loose_date(text: Any) -> date | None:
    """"August 28, 2007" / "12/20/2007" / "2 day of January, 2010" -> date."""
    if isinstance(text, date):
        return text
    if text is None:
        return None
    s = str(text)
    m = re.search(r"(\d{1,2})\s*/\s*(\d{1,2})\s*/\s*(\d{4})", s)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
        except ValueError:
            return None
    m = re.search(r"([A-Za-z]+)\s+(\d{1,2})\s*,?\s*(\d{4})", s)
    if m and m.group(1).lower() in _MONTHS:
        try:
            return date(int(m.group(3)), _MONTHS.index(m.group(1).lower()) + 1, int(m.group(2)))
        except ValueError:
            return None
    m = re.search(r"(\d{1,2})\s*day of\s*([A-Za-z]+)\s*,?\s*(\d{4})", s, re.IGNORECASE)
    if m and m.group(2).lower() in _MONTHS:
        try:
            return date(int(m.group(3)), _MONTHS.index(m.group(2).lower()) + 1, int(m.group(1)))
        except ValueError:
            return None
    return None


def check_nri_arithmetic(royalty: Any, orri: Any, nri: Any) -> tuple[str, Any]:
    """NRI must equal 1 - royalty - ORRI. Computable, so a difference is a
    MISMATCH against the workbook's own inputs, not an opinion."""
    r = parse_fraction_text(str(royalty)) if royalty is not None else None
    o = parse_fraction_text(str(orri)) if orri is not None else Fraction(0)
    if r is None:
        return UNVERIFIABLE, None
    expected = Fraction(1) - r - (o or Fraction(0))
    if isinstance(nri, str) and nri.strip().startswith("="):
        # The template's own =1-G-W formula IS the rule; nothing to contradict.
        return CONFIRMED, expected
    actual = parse_fraction_text(str(nri)) if nri is not None else None
    if actual is None:
        return UNVERIFIABLE, expected
    if abs(actual - expected) <= Fraction(1, 10**6):
        return CONFIRMED, expected
    return MISMATCH, expected


def check_recording_against_dpu(lease_no: str, book: Any, page: Any,
                                dpu_by_lease: dict[str, tuple[str | None, str | None]]
                                ) -> tuple[str, Any]:
    """Ownership cols K/L must equal the DPU Exhibit A recording exactly."""
    entry = dpu_by_lease.get(str(lease_no))
    if entry is None:
        return UNVERIFIABLE, None
    src_book, src_page = entry
    if src_book is None or src_page is None:
        return UNVERIFIABLE, None
    if book is None and page is None:
        return UNVERIFIABLE, f"Vol {src_book}, Pg {src_page}"
    same = (str(book).strip() == str(src_book) and str(page).strip() == str(src_page))
    return (CONFIRMED if same else MISMATCH), f"Vol {src_book}, Pg {src_page}"


def check_date_against_xref(workbook_date: Any, xref_serial: Any) -> tuple[str, Any]:
    """A contract's effective date must match the XREF's AGMT DATE serial."""
    src = excel_serial_to_date(xref_serial)
    got = parse_loose_date(workbook_date)
    if src is None:
        return UNVERIFIABLE, None
    if got is None:
        return UNVERIFIABLE, src.isoformat()
    return (CONFIRMED if got == src else MISMATCH), src.isoformat()


# ---------------------------------------------------------------------------
# Audit index
# ---------------------------------------------------------------------------

_CELL_RE = re.compile(r"^([A-Z]{1,3})(\d{1,7})$")
_ROW_RE = re.compile(r"^row\s+(\d+)$", re.IGNORECASE)
_PAGE_RE = re.compile(r"p\.?\s*(\d+)", re.IGNORECASE)


@dataclass
class AuditCite:
    sheet: str
    location: str
    source_type: str
    source_reference: str
    extracted_text: str = ""

    @property
    def cell(self) -> str | None:
        return self.location if _CELL_RE.match(self.location or "") else None

    @property
    def row(self) -> int | None:
        m = _ROW_RE.match(self.location or "")
        return int(m.group(1)) if m else None

    @property
    def page(self) -> int | None:
        m = _PAGE_RE.search(self.extracted_text or "")
        return int(m.group(1)) if m else None


def read_audit_cites(workbook) -> list[AuditCite]:
    if "DD_Audit_Trail" not in workbook.sheetnames:
        return []
    ws = workbook["DD_Audit_Trail"]
    out = []
    for r in range(2, ws.max_row + 1):
        if not ws.cell(r, 1).value:
            continue
        out.append(AuditCite(
            sheet=str(ws.cell(r, 1).value).strip(),
            location=str(ws.cell(r, 2).value or "").strip(),
            source_type=str(ws.cell(r, 3).value or "").strip(),
            source_reference=str(ws.cell(r, 4).value or "").strip(),
            extracted_text=str(ws.cell(r, 6).value or ""),
        ))
    return out


# ---------------------------------------------------------------------------
# The run: every client-facing sheet, every audited cell
# ---------------------------------------------------------------------------

_OWN = "Ownership Report"
_OWN_COL = {"lease_no": 2, "lessor": 5, "royalty": 7, "book": 11, "page": 12,
            "mi": 19, "wi": 20, "nri": 22, "orri": 23}
_OWN_DATA_START = 8


def _cell_name(col: int, row: int) -> str:
    from openpyxl.utils import get_column_letter
    return f"{get_column_letter(col)}{row}"


def check_ownership_report(workbook, index: SourceIndex, cites: list[AuditCite],
                           dpu_by_lease, report: TruthReport) -> None:
    """Recording vs the DPU, NRI vs its own inputs, MI/WI vs the cited opinion."""
    if _OWN not in workbook.sheetnames:
        return
    ws = workbook[_OWN]
    source_by_row = {c.row: c for c in cites if c.sheet == _OWN and c.row is not None}

    for row in range(_OWN_DATA_START, ws.max_row + 1):
        lease_no = ws.cell(row, _OWN_COL["lease_no"]).value
        if not lease_no:
            continue
        cite = source_by_row.get(row)
        src_path = index.resolve(cite.source_reference) if cite else None
        src_name = src_path.name if src_path else (cite.source_reference if cite else "(no cite)")

        # 1. Recording Vol/Page against the DPU's Exhibit A — exact, computable.
        book, page = ws.cell(row, _OWN_COL["book"]).value, ws.cell(row, _OWN_COL["page"]).value
        if book is not None or page is not None:
            outcome, src_value = check_recording_against_dpu(lease_no, book, page, dpu_by_lease)
            report.add(TruthFinding(
                _OWN, f"K{row}/L{row}", "Record Book/Page", f"Vol {book}, Pg {page}",
                src_value, outcome, source_file="DPU Exhibit A",
                detail="" if outcome != UNVERIFIABLE else
                       f"lease {lease_no} not named in the DPU Exhibit A"))

        # 2. NRI against the workbook's own royalty/ORRI — arithmetic.
        nri = ws.cell(row, _OWN_COL["nri"]).value
        if nri is not None:
            outcome, expected = check_nri_arithmetic(
                ws.cell(row, _OWN_COL["royalty"]).value,
                ws.cell(row, _OWN_COL["orri"]).value, nri)
            report.add(TruthFinding(
                _OWN, f"V{row}", "NRI = 1-royalty-ORRI", nri, expected, outcome,
                source_file="(computed from G/W)",
                detail="" if outcome != UNVERIFIABLE else "royalty absent, so NRI is not computable"))

        # 3. MI / WI against the opinion the audit trail cites.
        for key, label in (("mi", "MI Value"), ("wi", "WI Value")):
            value = ws.cell(row, _OWN_COL[key]).value
            if value is None:
                continue
            cell = _cell_name(_OWN_COL[key], row)
            if src_path is None:
                report.add(TruthFinding(
                    _OWN, cell, label, value, None, UNVERIFIABLE, source_file=src_name,
                    detail=(f"cited source {src_name!r} is not a document on disk"
                            if cite else "no audit cite for this row")))
                continue
            fraction = parse_fraction_text(str(value).lstrip("="))
            text = index.text(src_path)
            candidates = [str(value).lstrip("=")]
            if fraction is not None:
                candidates.append(f"{fraction.numerator}/{fraction.denominator}")
                candidates.append(f"{float(fraction):.8f}".lstrip("0"))
            if any(states_value(text, c) for c in candidates):
                report.add(TruthFinding(_OWN, cell, label, value, value, CONFIRMED,
                                        source_file=src_name))
            else:
                report.add(TruthFinding(
                    _OWN, cell, label, value, None, UNVERIFIABLE, source_file=src_name,
                    detail=("value not located in the opinion text; interests are stated as prose "
                            "formulas, so absence of the literal string is not a contradiction")))


def check_cell_level_cites(workbook, index: SourceIndex, cites: list[AuditCite],
                           report: TruthReport, skip_sheets=(_OWN,)) -> None:
    """Every audit row naming a specific cell AND a document (Agreements, Unit
    and Pooling, and any other sheet that cites one)."""
    for cite in cites:
        if cite.sheet in skip_sheets or not cite.cell:
            continue
        if cite.sheet not in workbook.sheetnames:
            continue
        value = workbook[cite.sheet][cite.cell].value
        field_name = (cite.extracted_text.split("@")[0].split(":")[0].strip() or cite.location)
        if value is None or str(value).strip() == "":
            continue
        src_path = index.resolve(cite.source_reference)
        if src_path is None:
            report.add(TruthFinding(
                cite.sheet, cite.cell, field_name, value, None, UNVERIFIABLE,
                source_file=cite.source_reference[:40],
                detail=("cited source is not a document on disk: "
                        + cite.source_reference.split(" + ")[0][:36])))
            continue
        text = index.page_text(src_path, cite.page)
        if states_value(text, value):
            report.add(TruthFinding(cite.sheet, cite.cell, field_name, value, value,
                                    CONFIRMED, source_file=src_path.name,
                                    source_page=f"p.{cite.page}" if cite.page else ""))
            continue
        whole = index.text(src_path)
        if cite.page and states_value(whole, value):
            report.add(TruthFinding(
                cite.sheet, cite.cell, field_name, value, value, CONFIRMED,
                source_file=src_path.name, source_page="(other page)",
                detail=f"stated in the instrument, but not on the cited p.{cite.page}"))
        else:
            report.add(TruthFinding(
                cite.sheet, cite.cell, field_name, value, None, UNVERIFIABLE,
                source_file=src_path.name,
                source_page=f"p.{cite.page}" if cite.page else "",
                detail=("value not located in the source text (OCR is lossy and instruments "
                        "paraphrase; not a contradiction)")))


def check_unaudited_sheets(workbook, cites: list[AuditCite], report: TruthReport,
                           client_sheets: list[str]) -> None:
    """Sheets with populated client cells but no cell+document cite at all."""
    audited = {c.sheet for c in cites if c.location}
    for sheet in client_sheets:
        if sheet not in workbook.sheetnames or sheet in report.per_sheet:
            continue
        ws = workbook[sheet]
        populated = sum(1 for row in ws.iter_rows() for c in row
                        if c.value not in (None, "") and str(c.value).strip() not in ("-", "--"))
        if not populated:
            continue
        report.add(TruthFinding(
            sheet, "(sheet)", "all cells", f"{populated} populated cell(s)", None,
            UNVERIFIABLE, detail=("no audit cite names a source document for this sheet"
                                  if sheet not in audited else
                                  "audit cites for this sheet are row/region-level, not cell+page")))


def run_source_truth(workbook, search_roots, dpu_by_lease=None,
                     ocr_fn=None, client_sheets=None) -> TruthReport:
    """Re-read every cited source and confirm the workbook against it."""
    report = TruthReport()
    index = SourceIndex(search_roots, ocr_fn=ocr_fn)
    cites = read_audit_cites(workbook)
    check_ownership_report(workbook, index, cites, dpu_by_lease or {}, report)
    check_cell_level_cites(workbook, index, cites, report)
    check_unaudited_sheets(workbook, cites, report,
                           client_sheets or [s for s in workbook.sheetnames
                                             if s != "DD_Audit_Trail"])
    return report


def truth_table(report: TruthReport) -> str:
    lines = [f"SOURCE TRUTH - {report.summary()}", ""]
    header = "sheet".ljust(32) + "confirmed".rjust(10) + "MISMATCH".rjust(10) + "unverif.".rjust(10)
    lines.append(header)
    total = SheetTruth("TOTAL")
    for sheet in sorted(report.per_sheet):
        s = report.per_sheet[sheet]
        lines.append(sheet.ljust(32) + str(s.confirmed).rjust(10)
                     + str(s.mismatched).rjust(10) + str(s.unverifiable).rjust(10))
        total.confirmed += s.confirmed
        total.mismatched += s.mismatched
        total.unverifiable += s.unverifiable
    lines.append("TOTAL".ljust(32) + str(total.confirmed).rjust(10)
                 + str(total.mismatched).rjust(10) + str(total.unverifiable).rjust(10))
    lines.append("")
    if report.mismatches:
        lines.append(f"MISMATCHES ({len(report.mismatches)}) - the workbook contradicts its source:")
        lines.extend("  " + f.describe() for f in report.mismatches)
    else:
        lines.append("MISMATCHES (0): no cell contradicts its cited source.")
    return "\n".join(lines)
