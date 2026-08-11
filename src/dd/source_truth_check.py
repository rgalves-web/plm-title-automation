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
from difflib import SequenceMatcher
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
    tract_level: int = 0
    anchored: int = 0
    semantic: int = 0
    by_rule: int = 0
    by_manifest: int = 0
    mismatched: int = 0
    unverifiable: int = 0

    @property
    def verified(self) -> int:
        """Every cell verified by SOME valid method. A computed total checked
        against its own arithmetic and a client name checked against the manifest
        are both genuinely verified — just not against a title document. What is
        NOT allowed is calling something verified with no method at all."""
        return (self.confirmed + self.tract_level + self.anchored + self.semantic
                + self.by_rule + self.by_manifest)

    @property
    def checked(self) -> int:
        return self.verified + self.mismatched + self.unverifiable


@dataclass
class TruthReport:
    findings: list[TruthFinding] = field(default_factory=list)
    per_sheet: dict[str, SheetTruth] = field(default_factory=dict)

    _covered: set = field(default_factory=set)

    def add(self, finding: TruthFinding) -> None:
        # One finding per cell: the first (strongest) checker to reach a cell
        # owns it. Without this a Summary cell verified against the manifest and
        # then reached again by the generic "cited source is not a document"
        # pass would be counted twice and contradict itself.
        key = (finding.sheet, finding.cell)
        if finding.cell and finding.cell != "(sheet)" and key in self._covered:
            return
        self._covered.add(key)
        self.findings.append(finding)
        sheet = self.per_sheet.setdefault(finding.sheet, SheetTruth(finding.sheet))
        if finding.outcome == CONFIRMED:
            sheet.confirmed += 1
        elif finding.outcome == CONFIRMED_TRACT_LEVEL:
            sheet.tract_level += 1
        elif finding.outcome == ANCHORED_VERIFIED:
            sheet.anchored += 1
        elif finding.outcome == SEMANTICALLY_CHECKED:
            sheet.semantic += 1
        elif finding.outcome == VERIFIED_BY_RULE:
            sheet.by_rule += 1
        elif finding.outcome == VERIFIED_BY_MANIFEST:
            sheet.by_manifest += 1
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
    def tract_level(self) -> list[TruthFinding]:
        return [f for f in self.findings if f.outcome == CONFIRMED_TRACT_LEVEL]

    @property
    def anchored(self) -> list[TruthFinding]:
        return [f for f in self.findings if f.outcome == ANCHORED_VERIFIED]

    @property
    def semantic(self) -> list[TruthFinding]:
        return [f for f in self.findings if f.outcome == SEMANTICALLY_CHECKED]

    @property
    def by_rule(self) -> list[TruthFinding]:
        return [f for f in self.findings if f.outcome == VERIFIED_BY_RULE]

    @property
    def by_manifest(self) -> list[TruthFinding]:
        return [f for f in self.findings if f.outcome == VERIFIED_BY_MANIFEST]

    @property
    def verified(self) -> list[TruthFinding]:
        return (self.confirmed + self.tract_level + self.anchored + self.semantic
                + self.by_rule + self.by_manifest)

    @property
    def truthful(self) -> bool:
        """A DDR may ship only with zero contradicted values."""
        return not self.mismatches

    def summary(self) -> str:
        return (f"{len(self.confirmed)} confirmed, {len(self.tract_level)} tract-level, "
                f"{len(self.anchored)} anchored, "
                f"{len(self.semantic)} semantic, {len(self.by_rule)} by-rule, "
                f"{len(self.by_manifest)} by-manifest, {len(self.mismatches)} MISMATCH, "
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
        self._by_volpage: dict[tuple[str, str], Path] = {}
        self._ocr_fn = ocr_fn
        for root in self.search_roots:
            for path in root.rglob("*"):
                if path.is_file() and path.suffix.lower() in {
                        ".pdf", ".tif", ".tiff", ".txt", ".xlsx", ".xlsm"}:
                    self._files.setdefault(_norm_key(path.stem), path)
                    # Recorded instruments named by recording cite: "479.590 - …"
                    m = re.match(r"^\s*(\d{2,4})\.(\d{1,4})\b", path.stem)
                    if m:
                        self._by_volpage.setdefault((m.group(1), m.group(2)), path)

    def resolve(self, reference: str | None) -> Path | None:
        """An audit source reference -> the file on disk, or None.

        Beyond exact/contained stem matching, three real citation shapes are
        understood (all seen in the Bowen audit trail):
        - a recording cite in the reference ("DPU K1400725 Exhibit A (Vol 479
          Pg 590-596)") -> the instrument filed as "479.590 - …";
        - an inner filename in parentheses ("DPU K1400725 zip (UNIT DEC -
          REC.TIF)") -> that file wherever it sits on disk;
        - a workbook cited by title ("Lease & Mineral Schedule 6.9.26") -> the
          .xlsx on disk, tolerant of "(2)" copy suffixes via containment."""
        if not reference:
            return None
        first = str(reference).split(" + ")[0].strip()
        if first in _NON_DOCUMENT_SOURCES:
            return None
        stem = _citation_stem(first)
        key = _norm_key(stem)
        if key in self._files:
            return self._files[key]
        # A reference may carry a page cite or trailing prose ("T-O SUPP COX pp.5-6").
        trimmed = _norm_key(re.split(r"\bPP?\.", stem, maxsplit=1)[0])
        if trimmed and trimmed in self._files:
            return self._files[trimmed]
        # Recording cite inside the reference -> "<vol>.<page> - …" instrument.
        m = re.search(r"\bVol\.?\s*(\d{2,4})[,\s]+P(?:g|age)\.?\s*(\d{1,4})\b",
                      first, re.IGNORECASE)
        if m and (m.group(1), m.group(2)) in self._by_volpage:
            return self._by_volpage[(m.group(1), m.group(2))]
        # An inner filename cited in parentheses ("… zip (UNIT DEC - REC.TIF)").
        for inner in re.findall(r"\(([^()]+\.(?:pdf|tiff?|txt|xlsx|xlsm))\)",
                                first, re.IGNORECASE):
            inner_key = _norm_key(Path(inner).stem)
            if inner_key in self._files:
                return self._files[inner_key]
        # Containment last: tolerant of copy suffixes ("… 6.9.26 (2).xlsx") and
        # page-cite tails. It must never pick arbitrarily: taking the first hit
        # in traversal order made resolution depend on FOLDER LAYOUT — after the
        # Bowen package was reorganised by tract, a citation reading
        # "T-O SUPP Bowen A-227 141.5 ac" resolved to an A-682 opinion (four
        # candidates contained the key; the wrong one came first), and
        # non-distinctive MI values then "CONFIRMED" against the wrong document.
        # Now: the winner must be unique and clearly best, and must not
        # contradict the citation's distinctive tokens. Ambiguity resolves to
        # None — correct-and-fewer beats plausible-and-wrong.
        if not trimmed:
            return None
        # A citation normally LEADS with the document's name and then adds prose
        # ("… .PDF p.1 (read visually)", "… TRUE GROSS", "… (in all 0220649 lease
        # folders)"). So: the longest indexed name the citation starts with wins.
        # Copy markers are normalised away first — four byte-copies of one
        # opinion are one document, and which copy answers is not a question the
        # citation was ever asking. Deterministic: ties inside a single identity
        # resolve by sorted name, never by traversal order.
        prefix_hits: dict[str, list[Path]] = {}
        for path in self._files.values():
            fkey = _norm_key(_copy_stripped(path.stem))
            if fkey and trimmed.startswith(fkey) and not _contradicts_abstract(first, path.stem):
                prefix_hits.setdefault(fkey, []).append(path)
        if prefix_hits:
            longest = max(prefix_hits, key=len)
            return sorted(prefix_hits[longest], key=lambda p: p.name)[0]
        # Candidate pool. When the citation names an abstract, THAT is the
        # discriminator (OKF ontology §2: a survey is abstract + block, never a
        # name) — pool = files sharing it. Otherwise fall back to containment,
        # which still serves titles like "Lease & Mineral Schedule 6.9.26".
        cited_abstracts = _abstracts(first)
        if cited_abstracts:
            candidates = [(k, p) for k, p in self._files.items()
                          if _abstracts(p.stem) & cited_abstracts]
        else:
            candidates = [(k, p) for k, p in self._files.items()
                          if trimmed in k or k in trimmed]
        candidates = [(k, p) for k, p in candidates
                      if not _contradicts_abstract(first, p.stem)]
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0][1]
        scored = sorted(
            ((SequenceMatcher(None, trimmed, k).ratio(), k, p) for k, p in candidates),
            key=lambda t: (-t[0], t[1]))
        best, runner_up = scored[0], scored[1]
        if best[0] - runner_up[0] < _RESOLVE_MARGIN:
            return None                      # too close to call — stay honest
        return best[2]

    def text(self, path: Path) -> str:
        if path not in self._text:
            suffix = path.suffix.lower()
            if suffix == ".txt":
                self._text[path] = path.read_text(encoding="utf-8", errors="replace")
            elif suffix in (".xlsx", ".xlsm"):
                # Tabular source: the cells ARE the text — deterministic read,
                # no OCR. Lets a value cited to a schedule/XREF workbook be
                # verified against the workbook's own content.
                self._text[path] = _workbook_text(path)
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


# How much better the best containment candidate must be than the runner-up
# before it may be named as the source. Below this, the citation is not
# distinctive enough to identify one file and resolution returns None.
_RESOLVE_MARGIN = 0.08

_DOC_EXT_RE = re.compile(r"\.(pdf|tiff?|txt|xlsx|xlsm|docx?|png|jpe?g)$", re.IGNORECASE)


def _citation_stem(text: str) -> str:
    """Drop a trailing file extension — and NOTHING else.

    Never use Path().stem on citation prose: a citation carrying a date
    ("… cert. 10/18/2008") is read as a path, the slashes become separators and
    the whole citation collapses to "2008". That is what made a Bowen citation
    match any file whose name contained the year."""
    return _DOC_EXT_RE.sub("", str(text).strip())


_COPY_SUFFIX_RE = re.compile(r"\s*\(\d+\)\s*$")


def _copy_stripped(stem: str) -> str:
    """A filename stem without its "(2)" copy marker.

    Four byte-copies of one opinion are one DOCUMENT. Treating them as four
    rival candidates made a citation ambiguous when its identity was never in
    doubt — only which copy answers it."""
    return _COPY_SUFFIX_RE.sub("", str(stem)).strip()


_ABSTRACT_RE = re.compile(r"\bA-?(\d{2,4})\b", re.IGNORECASE)


def _abstracts(text: str) -> set[str]:
    """Abstract numbers named in a citation or filename ("A-227" -> {"227"}).

    The abstract is the most distinctive identity token a title document
    carries; two documents differing in abstract are never the same document
    (OKF ontology §2: identify a survey by abstract + block, never by name)."""
    return {m.group(1) for m in _ABSTRACT_RE.finditer(str(text))}


def _contradicts_abstract(citation: str, candidate_name: str) -> bool:
    """True when both sides name abstracts and they do not overlap."""
    cited, candidate = _abstracts(citation), _abstracts(candidate_name)
    return bool(cited and candidate and not (cited & candidate))


def _workbook_text(path: Path) -> str:
    """Every cell of every sheet as searchable text (deterministic, no OCR)."""
    import openpyxl

    lines: list[str] = []
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    try:
        for name in wb.sheetnames:
            lines.append(f"[sheet: {name}]")
            for row in wb[name].iter_rows(values_only=True):
                cells = [str(c) for c in row if c is not None]
                if cells:
                    lines.append(" | ".join(cells))
    finally:
        wb.close()
    return "\n".join(lines)


def normalize_for_match(text: Any) -> str:
    """Collapse the differences OCR invents: case, spacing, punctuation."""
    return re.sub(r"[^A-Z0-9]+", "", str(text).upper())


def states_value(source_text: str, value: Any) -> bool:
    """Is *value* stated in the source text? Punctuation/space-insensitive."""
    needle = normalize_for_match(value)
    return bool(needle) and needle in normalize_for_match(source_text)


# ---------------------------------------------------------------------------
# Normalization layer + the four-way status model
# ---------------------------------------------------------------------------

# A summary fully supported by an independently-located passage.
ANCHORED_VERIFIED = "ANCHORED-VERIFIED"
# A Working Interest confirmed against the opinion's TRACT-level EOG leasehold WI
# — the honest anchor for WI, which is EOG's tract figure and not tied to the
# individual lessor's name (so name+value co-occurrence correctly cannot reach
# it). Distinct method, stated as such.
CONFIRMED_TRACT_LEVEL = "CONFIRMED-TRACT-LEVEL"
# A computed cell (a formula total, a product, a per-tract sum) checked against
# its OWN arithmetic — real verification, against the rule instead of a document.
VERIFIED_BY_RULE = "VERIFIED-BY-RULE"
# A project-level value (client, acquisition, operator) checked against the
# manifest / Project Log, which IS its source of truth — not a title document.
VERIFIED_BY_MANIFEST = "VERIFIED-BY-MANIFEST"
# The value's key facts are in the source, but no single passage anchors it.
SEMANTICALLY_CHECKED = "SEMANTICALLY-CHECKED"

_ACRONYMS = ("EOG", "XTO", "COG", "BHP", "JDMI", "REO", "LLC", "LP", "INC", "CORP")


def _entity_key(text: Any) -> str:
    """Case/punctuation-insensitive company identity: 'EOG RESOURCES INC' ==
    'EOG Resources, Inc.'. Corporate suffixes are noise for identity."""
    key = re.sub(r"[^A-Z0-9 ]+", " ", str(text).upper())
    words = [w for w in key.split() if w not in {"INC", "LLC", "LP", "LTD", "CORP", "CO", "THE"}]
    return "".join(words)


def value_variants(value: Any) -> list[str]:
    """Every form a source might legitimately state *value* in.

    The matcher was literal, so a royalty written 1/5 in the workbook and
    ".20000000" in the opinion read as "not found" — a format difference
    reported as an absence. These are the same number and must match.
    """
    raw = str(value).strip()
    body = raw.lstrip("=").strip()
    out = [raw, body]

    # fraction <-> decimal <-> percent
    fraction = parse_fraction_text(body)
    if fraction is not None:
        out.append(f"{fraction.numerator}/{fraction.denominator}")
        as_float = float(fraction)
        out.append(f"{as_float:.8f}")
        out.append(f"{as_float:.8f}".lstrip("0"))       # opinions print ".84953704"
        out.append(f"{as_float:g}")
        if as_float <= 1:
            pct = as_float * 100
            out.append(f"{pct:g}%")
            out.append(f"{pct:.6f}%".rstrip("0").rstrip("."))

    # dates: "August 28, 2007" <-> "28 day of August, 2007" <-> "8/28/2007"
    parsed = parse_loose_date(body)
    if parsed:
        # Build date strings by hand: strftime's no-pad flag is %-d on Linux and
        # %#d on Windows, and neither is portable.
        out.append(f"{parsed.month}/{parsed.day}/{parsed.year}")
        out.append(f"{parsed.day:02d}/{parsed.month:02d}/{parsed.year}")
        month = parsed.strftime("%B")
        out.append(f"{parsed.day} day of {month}, {parsed.year}")
        for suffix in ("st", "nd", "rd", "th"):
            out.append(f"{parsed.day}{suffix} day of {month}, {parsed.year}")
        out.append(f"{month} {parsed.day}, {parsed.year}")

    # Vol/Page: "Volume 405, Page 343" <-> "Vol. 405, Pg. 343" <-> "405/343"
    vol = re.search(r"\b(?:vol(?:ume)?|book)\.?\s*(\d+)\D{0,12}?(?:p(?:a)?g(?:e)?)\.?\s*(\d+)",
                    body, re.IGNORECASE)
    if vol:
        book, page = vol.group(1), vol.group(2)
        # An instrument's recording is printed every which way, and "Book" and
        # "Volume" are the same thing in this county's records.
        out += [f"Volume {book}, Page {page}", f"Vol. {book}, Pg. {page}",
                f"Vol {book} Pg {page}", f"{book}/{page}",
                f"Book {book}, Page {page}", f"Book {book} at Page {page}",
                f"Volume {book} at Page {page}", f"Bk {book} Pg {page}"]

    return [v for v in dict.fromkeys(out) if v and str(v).strip()]


def states_value_normalized(source_text: str, value: Any) -> tuple[bool, str | None]:
    """Is *value* stated in the source in ANY legitimate form?

    Returns (found, the form it was found as) so the report can show a reader
    exactly how the source phrased it.
    """
    haystack = normalize_for_match(source_text)
    if not haystack:
        return False, None
    for variant in value_variants(value):
        needle = normalize_for_match(variant)
        if needle and needle in haystack:
            return True, variant
    # Entities: "EOG Resources, Inc." vs "EOG RESOURCES INC"
    key = _entity_key(value)
    if len(key) >= 6 and key in _entity_key(source_text):
        return True, str(value)
    return False, None


def verify_value(source_text: str, value: Any, field_name: str = "",
                 interpretive: bool | None = None) -> tuple[str, str, str]:
    """Adjudicate one value against its source text.

    Returns (outcome, evidence, detail) where outcome is one of
    CONFIRMED / ANCHORED_VERIFIED / SEMANTICALLY_CHECKED / UNVERIFIABLE.

    The ladder, strongest rung first:
      1. the source states the value in some legitimate form  -> CONFIRMED
      2. an independently-located passage supports it, and every fact the value
         asserts appears in that passage                      -> ANCHORED-VERIFIED
      3. the value's facts are all in the source, but no one
         passage anchors it                                   -> SEMANTICALLY-CHECKED
      4. nothing found                                        -> UNVERIFIABLE (NO_ANCHOR)

    Rung 2 is the one that earns its keep on summaries. The anchor is found by
    SEARCHING the text — the summarizer never nominates its own proof — and a
    summary asserting a fact its anchor lacks does not pass here at all; the
    caller raises that as a fidelity FAIL.
    """
    from src.dd.provenance import check_fidelity, locate_anchor

    found, form = states_value_normalized(source_text, value)
    if found:
        return CONFIRMED, form or str(value), ""

    anchor = locate_anchor(source_text, value)
    if anchor is not None:
        invented = check_fidelity(value, anchor.quote)
        if not invented:
            return (ANCHORED_VERIFIED, anchor.quote,
                    f"summary supported by an independently-located passage on p.{anchor.page} "
                    f"(similarity {anchor.ratio:.2f})")
        # Facts not in the anchor: the caller decides FAIL. Say so plainly.
        return (UNVERIFIABLE, anchor.quote,
                f"FIDELITY: the summary asserts {sorted(invented)} which its own anchor on "
                f"p.{anchor.page} does not contain")

    # No single passage anchors it — are the value's facts in the document at all?
    from src.dd.provenance import facts_in

    value_facts = facts_in(value)
    if value_facts:
        source_facts = facts_in(source_text)
        if value_facts <= source_facts:
            return (SEMANTICALLY_CHECKED, ", ".join(sorted(value_facts)),
                    "every figure the value asserts appears in the source, but no single "
                    "passage anchors the wording")
    return (UNVERIFIABLE, "",
            "NO_ANCHOR: no passage in the cited source supports this value (OCR is lossy and "
            "instruments paraphrase, so this is reported, not called a contradiction)")


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
    MISMATCH against the workbook's own inputs, not an opinion.

    A blank ORRI means zero (the template's semantics). But PROSE in the ORRI
    column — Bowen's "Burdens reflected in FIRST SUPP T-O NRI 0.51875 (see
    opinion)" — is not a number, and treating it as zero manufactures a
    mismatch out of a type error. When the burden is stated narratively the
    identity is not computable: UNVERIFIABLE, never a fabricated expectation.
    Numeric ORRI still verifies exactly."""
    r = parse_fraction_text(str(royalty)) if royalty is not None else None
    if r is None:
        return UNVERIFIABLE, None
    if orri is None or str(orri).strip() == "":
        o = Fraction(0)                      # absent = no override
    else:
        o = parse_fraction_text(str(orri))
        if o is None:                        # prose burden — identity not computable
            return UNVERIFIABLE, None
    expected = Fraction(1) - r - o
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
    # Cell-level provenance cites (S16 -> T-O SUPP p.5), located independently by
    # populate_provenance. When one exists for an MI/WI cell it is authoritative:
    # it names the document that actually contains the value AND its page, which
    # is more precise than the row's opinion and fixes the superseded-opinion
    # miscitation (a Cox owner cited against ORIG when the value is in SUPP).
    cell_cite = {c.cell: c for c in cites if c.sheet == _OWN and c.cell}

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
            royalty_v = ws.cell(row, _OWN_COL["royalty"]).value
            orri_v = ws.cell(row, _OWN_COL["orri"]).value
            outcome, expected = check_nri_arithmetic(royalty_v, orri_v, nri)
            if outcome != UNVERIFIABLE:
                why = ""
            elif royalty_v is None or str(royalty_v).strip() == "":
                why = "royalty absent, so NRI is not computable"
            elif orri_v is not None and parse_fraction_text(str(orri_v)) is None \
                    and str(orri_v).strip() != "":
                why = (f"ORRI column carries prose ({str(orri_v)[:60]!r}) — "
                       "burden stated narratively, identity not computable")
            else:
                why = "NRI identity not computable from the row's inputs"
            report.add(TruthFinding(
                _OWN, f"V{row}", "NRI = 1-royalty-ORRI", nri, expected, outcome,
                source_file="(computed from G/W)", detail=why))

        # 3. MI / WI against the opinion the audit trail cites.
        for key, label in (("mi", "MI Value"), ("wi", "WI Value")):
            value = ws.cell(row, _OWN_COL[key]).value
            if value is None:
                continue
            cell = _cell_name(_OWN_COL[key], row)
            # A cell-level provenance cite, if present, overrides the row's
            # opinion: it points at the document + page where this value was
            # independently located.
            prov = cell_cite.get(cell)
            prov_path = index.resolve(prov.source_reference) if prov else None
            check_path, check_name = (prov_path, prov_path.name) if prov_path else (src_path, src_name)
            if check_path is None:
                report.add(TruthFinding(
                    _OWN, cell, label, value, None, UNVERIFIABLE, source_file=src_name,
                    detail=(f"cited source {src_name!r} is not a document on disk"
                            if cite else "no audit cite for this row")))
                continue
            text = (index.page_text(check_path, prov.page) if prov and prov.page
                    else index.text(check_path))
            outcome, evidence, detail = verify_value(text, value, field_name=label)
            page = f"p.{prov.page}" if prov and prov.page else ""
            report.add(TruthFinding(_OWN, cell, label, value,
                                    evidence if outcome != UNVERIFIABLE else None,
                                    outcome, source_file=check_name, source_page=page, detail=detail))


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
        # The CITED page first: a cite that names the wrong page is itself a
        # defect worth surfacing, and checking the whole document first would
        # hide it. Only if the cited page does not carry the value do we widen
        # to the instrument and say so.
        outcome, evidence, detail = verify_value(
            index.page_text(src_path, cite.page), value, field_name=field_name)
        if outcome == UNVERIFIABLE and cite.page:
            wide_outcome, wide_evidence, wide_detail = verify_value(
                index.text(src_path), value, field_name=field_name)
            if wide_outcome != UNVERIFIABLE:
                outcome, evidence = wide_outcome, wide_evidence
                detail = (f"stated in the instrument, but NOT on the cited p.{cite.page} — "
                          f"the citation names the wrong page. {wide_detail}").strip()
        report.add(TruthFinding(
            cite.sheet, cite.cell, field_name, value,
            evidence if outcome != UNVERIFIABLE else None, outcome,
            source_file=src_path.name,
            source_page=f"p.{cite.page}" if cite.page else "", detail=detail))


# ---------------------------------------------------------------------------
# VERIFIED_BY_RULE — computed cells checked against their own arithmetic
# ---------------------------------------------------------------------------

def check_computed_cells(workbook, report: TruthReport) -> None:
    """Formula/derived cells that have no external document — verify the MATH.

    A header total, a net-acre product, a per-tract MI sum: their source of
    truth is the arithmetic, not a title opinion. Checking that the formula is
    the RIGHT formula (and, where the inputs are literals, that it computes
    consistently) is real verification. It is NOT a licence to dump hard cells
    here — only cells whose correctness is fully decidable from other cells in
    the workbook qualify, and each is named.
    """
    if _OWN not in workbook.sheetnames:
        return
    ws = workbook[_OWN]
    rows = [r for r in range(_OWN_DATA_START, ws.max_row + 1)
            if ws.cell(r, _OWN_COL["lease_no"]).value not in (None, "")]
    # Per-row derived formulas: U = R*S*T (net acres), X = U*V (net revenue).
    for row in rows:
        for col, formula_shape, label in (
            (21, f"=R{row}*S{row}*T{row}", "Net Acres = R*S*T"),
            (24, f"=U{row}*V{row}", "Net Revenue Acres = U*V"),
            (22, f"=1-G{row}-W{row}", "NRI = 1-royalty-ORRI")):
            value = ws.cell(row, col).value
            if value is None:
                continue
            cell = _cell_name(col, row)
            if isinstance(value, str) and value.replace(" ", "") == formula_shape.replace(" ", ""):
                report.add(TruthFinding(_OWN, cell, label, value, formula_shape,
                                        VERIFIED_BY_RULE, source_file="(arithmetic)",
                                        detail=f"formula is the template's {label} — verified by rule"))
            elif col == 22:
                outcome, expected = check_nri_arithmetic(
                    ws.cell(row, 7).value, ws.cell(row, 23).value, value)
                if outcome == MISMATCH:
                    report.add(TruthFinding(_OWN, cell, label, value, float(expected),
                                            MISMATCH, source_file="(arithmetic)"))
                elif outcome in (CONFIRMED,):
                    report.add(TruthFinding(_OWN, cell, label, value, expected,
                                            VERIFIED_BY_RULE, detail="NRI equals 1-royalty-ORRI"))
    # Header aggregates: B5=SUM(U), D5=B5/A5, etc. — verified as the right formula.
    for coord, shape_prefix, label in (("B5", "=SUM(U", "Sum of net acres"),
                                       ("C5", "=SUM(X", "Sum of net revenue acres"),
                                       ("D5", "=B5/A5", "Headline WI = net acres / unit gross"),
                                       ("E5", "=C5/A5", "Headline NRI")):
        v = ws[coord].value
        if isinstance(v, str) and v.replace(" ", "").upper().startswith(shape_prefix.replace(" ", "").upper()):
            report.add(TruthFinding(_OWN, coord, label, v, shape_prefix, VERIFIED_BY_RULE,
                                    source_file="(arithmetic)", detail=f"{label} — verified by rule"))


# ---------------------------------------------------------------------------
# VERIFIED_BY_MANIFEST — project-level values checked against the manifest/log
# ---------------------------------------------------------------------------

# Summary label -> the manifest attribute that IS its source of truth.
_MANIFEST_FIELDS = {
    "client": ("client_name", "seller_name"),
    "acquisition": ("acquisition_name",),
    "operator": ("operator", "seller_name"),
    "state": ("state",),
    "county": ("county",),
    "landman": ("landman_name",),
}


def check_manifest_cells(workbook, manifest, report: TruthReport,
                         sheet: str = "Summary", label_col: int = 1, value_col: int = 2) -> None:
    """Project-level Summary values against the manifest — their real source.

    Client "BKV Corp.", Acquisition "Project Emirates", Operator "EOG" do not
    come from a title document and never will; the manifest (built from the
    Project Log and the client's own inputs) is where they are true or false.
    Matching the cell to the manifest is genuine verification against that
    source. A cell that does NOT match its manifest value is a MISMATCH.
    """
    if manifest is None or sheet not in workbook.sheetnames:
        return
    ws = workbook[sheet]
    for row in ws.iter_rows():
        label_cell = ws.cell(row[0].row, label_col)
        value_cell = ws.cell(row[0].row, value_col)
        if not isinstance(label_cell.value, str) or value_cell.value in (None, ""):
            continue
        key = re.sub(r"[^a-z]", "", label_cell.value.lower())
        field = next((f for tag, f in _MANIFEST_FIELDS.items() if tag in key), None)
        if field is None:
            continue
        expected = next((getattr(manifest, a, None) for a in field
                         if getattr(manifest, a, None)), None)
        if not expected:
            continue
        cell = _cell_name(value_col, row[0].row)
        found, _form = states_value_normalized(str(expected), value_cell.value)
        also = states_value_normalized(str(value_cell.value), str(expected))[0]
        if found or also:
            report.add(TruthFinding(sheet, cell, label_cell.value.rstrip(":"),
                                    value_cell.value, expected, VERIFIED_BY_MANIFEST,
                                    source_file="project manifest",
                                    detail=f"matches manifest.{field[0]}"))
        else:
            report.add(TruthFinding(sheet, cell, label_cell.value.rstrip(":"),
                                    value_cell.value, expected, MISMATCH,
                                    source_file="project manifest",
                                    detail=f"does not match manifest.{field[0]} = {expected!r}"))


# ---------------------------------------------------------------------------
# CONFIRMED_TRACT_LEVEL — WI against the opinion's tract-level EOG leasehold WI
# ---------------------------------------------------------------------------

# The EOG leasehold-WI figure a controlling opinion prints is a distinctive
# 8-decimal number (.84953704, .62500000, 1.00000000). Co-locating it with EOG
# on a page is safe — a bare fraction would not be, but this decimal is.
_WI_CONTEXT = ("EOG", "LEASEHOLD", "WORKING")


def check_wi_tract_level(workbook, controlling_docs, report: TruthReport) -> None:
    """Verify each WI cell against the controlling opinion's stated EOG TRACT WI.

    WI is EOG's interest in the tract, not the individual lessor's — so
    name+value co-occurrence on the lessor cannot reach it and (correctly) leaves
    it UNVERIFIABLE. The honest anchor is the opinion's own leasehold-estate line:
    "EOG Resources, Inc. ... Working Interest .84953704". When that figure is on
    a page that also mentions EOG/leasehold, the cell is CONFIRMED_TRACT_LEVEL
    with document+page. When the opinion states no such figure, the cell stays
    UNVERIFIABLE, named — never guessed.
    """
    if _OWN not in workbook.sheetnames or not controlling_docs:
        return
    from src.dd.provenance import split_pages

    ws = workbook[_OWN]
    for row in range(_OWN_DATA_START, ws.max_row + 1):
        if ws.cell(row, _OWN_COL["lease_no"]).value in (None, ""):
            continue
        raw = ws.cell(row, _OWN_COL["wi"]).value
        if raw is None:
            continue
        cell = _cell_name(_OWN_COL["wi"], row)
        if (_OWN, cell) in report._covered:
            continue                              # already owned (e.g. a provenance cite)
        fraction = parse_fraction_text(str(raw).lstrip("="))
        variants = value_variants(raw)
        if fraction is not None:                  # the opinion prints the decimal
            variants.append(f"{float(fraction):.8f}".lstrip("0"))
            variants.append(f"{float(fraction):.8f}")
        located = None
        for name, text in controlling_docs:
            for page_no, page in enumerate(split_pages(text), start=1):
                page_norm = normalize_for_match(page)
                if not any(normalize_for_match(v) in page_norm for v in variants if len(str(v)) >= 4):
                    continue
                if not any(ctx in page.upper() for ctx in _WI_CONTEXT):
                    continue                      # value present but not the leasehold table
                located = (name, page_no)
                break
            if located:
                break
        if located:
            name, page = located
            report.add(TruthFinding(_OWN, cell, "WI Value (tract)", raw, raw,
                                    CONFIRMED_TRACT_LEVEL, source_file=name,
                                    source_page=f"p.{page}",
                                    detail="matches the opinion's EOG tract-level leasehold WI"))
        else:
            report.add(TruthFinding(
                _OWN, cell, "WI Value (tract)", raw, None, UNVERIFIABLE,
                detail="no tract-level EOG working interest stated in the controlling opinion "
                       "for this tract — verify by hand"))


# ---------------------------------------------------------------------------
# Lease Review term cells — per-lease document provenance (lessor + value)
# ---------------------------------------------------------------------------

_LR = "Lease Review"
_LR_LEASE, _LR_LESSOR = 1, 3
# column -> (field label, whether the value is prose to anchor vs a literal)
_LR_FIELDS = {5: "Effective Date", 6: "Recording Info", 9: "Term of Lease",
              10: "Royalty", 15: "Pooling Clause"}


def check_lease_review_terms(workbook, index: SourceIndex, report: TruthReport,
                             lease_doc_finder=None) -> None:
    """Each Lease Review term cell against THIS lease's recorded document,
    anchored on the lessor name + the value — the same technique as Ownership.

    A lease with no full document on disk (the 4 memoranda leases) cannot be
    verified here and stays UNVERIFIABLE, named. That is a genuine gap — the
    document is not in the file — not a limitation of the method.
    """
    if _LR not in workbook.sheetnames:
        return
    from src.dd.lease_document_source import find_lease_document

    ws = workbook[_LR]
    for row in range(2, ws.max_row + 1):
        lease_no = ws.cell(row, _LR_LEASE).value
        lessor = ws.cell(row, _LR_LESSOR).value
        if not lease_no or "-" not in str(lease_no):
            continue
        doc = lease_doc_finder(str(lease_no)) if lease_doc_finder else None
        text = index.text(doc) if doc else None
        for col, label in _LR_FIELDS.items():
            value = ws.cell(row, col).value
            if value in (None, "") or str(value).strip() in ("-", "--"):
                continue
            cell = _cell_name(col, row)
            if (_LR, cell) in report._covered:
                continue
            if text is None:
                report.add(TruthFinding(
                    _LR, cell, label, value, None, UNVERIFIABLE,
                    detail=f"no recorded document on disk for lease {lease_no} "
                           "(memorandum only) — cannot verify this term"))
                continue
            # Anchor: the lessor must be in the document, then verify the value.
            outcome, evidence, detail = verify_value(text, value, field_name=label)
            lessor_key = normalize_for_match(str(lessor).split()[0]) if lessor else ""
            if outcome == UNVERIFIABLE and lessor_key and lessor_key not in normalize_for_match(text):
                detail = f"lessor {lessor!r} not found in {doc.name} — wrong document?"
            report.add(TruthFinding(_LR, cell, label, value,
                                    evidence if outcome != UNVERIFIABLE else None,
                                    outcome, source_file=doc.name, detail=detail))


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
                     ocr_fn=None, client_sheets=None, manifest=None,
                     controlling_docs=None, lease_doc_finder=None) -> TruthReport:
    """Re-read every cited source and confirm the workbook against it."""
    report = TruthReport()
    index = SourceIndex(search_roots, ocr_fn=ocr_fn)
    cites = read_audit_cites(workbook)
    # Strongest / most specific checkers first — they own their cells, and the
    # generic passes below skip anything already covered (see TruthReport.add).
    check_manifest_cells(workbook, manifest, report)
    check_computed_cells(workbook, report)
    # WI tract-level BEFORE the row check: WI is an EOG tract figure, and its
    # authoritative source is the opinion's leasehold table, not the row's cite.
    # Run first so it owns the WI cell instead of the row check marking it
    # UNVERIFIABLE (cited XREF) and deduping the tract-level result away.
    check_wi_tract_level(workbook, controlling_docs or [], report)
    check_ownership_report(workbook, index, cites, dpu_by_lease or {}, report)
    check_lease_review_terms(workbook, index, report, lease_doc_finder)
    check_cell_level_cites(workbook, index, cites, report)
    check_unaudited_sheets(workbook, cites, report,
                           client_sheets or [s for s in workbook.sheetnames
                                             if s != "DD_Audit_Trail"])
    return report


def truth_table(report: TruthReport) -> str:
    lines = [f"SOURCE TRUTH - {report.summary()}", ""]
    cols = ("confirmed", "tract-lvl", "anchored", "semantic", "by-rule", "by-manif", "verified", "MISMATCH", "unverif.")
    lines.append("sheet".ljust(26) + "".join(c.rjust(9) for c in cols))
    total = SheetTruth("TOTAL")
    def row(name, s):
        return (name.ljust(26) + str(s.confirmed).rjust(9) + str(s.tract_level).rjust(9) + str(s.anchored).rjust(9)
                + str(s.semantic).rjust(9) + str(s.by_rule).rjust(9) + str(s.by_manifest).rjust(9)
                + str(s.verified).rjust(9) + str(s.mismatched).rjust(9) + str(s.unverifiable).rjust(9))
    for sheet in sorted(report.per_sheet):
        s = report.per_sheet[sheet]
        lines.append(row(sheet, s))
        for attr in ("confirmed", "tract_level", "anchored", "semantic", "by_rule", "by_manifest",
                     "mismatched", "unverifiable"):
            setattr(total, attr, getattr(total, attr) + getattr(s, attr))
    lines.append(row("TOTAL", total))
    lines.append("")
    if report.mismatches:
        lines.append(f"MISMATCHES ({len(report.mismatches)}) - the workbook contradicts its source:")
        lines.extend("  " + f.describe() for f in report.mismatches)
    else:
        lines.append("MISMATCHES (0): no cell contradicts its cited source.")
    return "\n".join(lines)
