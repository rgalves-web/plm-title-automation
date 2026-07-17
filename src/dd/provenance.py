"""Cell-level provenance: which document, which page, which passage.

The audit trail's job is to let a reader land on the exact page that supports a
cell. Today it mostly cannot: of the writer's record sites, only three name a
document and none name a page, so 56 of 67 unverifiable cells are unverifiable
for want of a citation rather than want of truth. This module supplies the
missing piece — a CellSource carrying document + page + the verbatim passage —
and, crucially, a way to FIND the page that does not trust the extractor.

Independence, and why it is the whole point
-------------------------------------------
A summarizer must not choose its own proof. If the LLM says "this came from p.2"
and we record p.2, we have recorded the LLM's opinion twice and verified nothing.
So `locate_page` and `locate_anchor` SEARCH the source text for a passage
supporting the value, using deterministic matching. When the search finds
nothing, that is reported (NO_ANCHOR) rather than papered over with the
extractor's own claim.

Not every source is a PDF. A lease number legitimately comes from the XREF
spreadsheet, and "the XREF" is a perfectly good citation — it is simply verified
by re-reading a cell rather than OCR. StructuredSource carries that case so those
values stop being lumped in with "no source at all".
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

# How alike a candidate passage must be to count as supporting the value.
# Tuned against real OCR: below ~0.55 the "match" is noise, and a bad anchor is
# worse than none — it would let a wrong summary look proven.
ANCHOR_MIN_RATIO = 0.55
# A window of source text roughly the size of a clause.
ANCHOR_WINDOW = 320

NO_ANCHOR = "NO_ANCHOR"

_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9./%-]*")
# Facts a summary asserts: numbers, acreages, percentages, fractions.
_FACT_RE = re.compile(r"\b\d+(?:\.\d+)?\s*%|\b\d+\s*/\s*\d+\b|\b\d[\d,]*(?:\.\d+)?\b")


@dataclass(frozen=True)
class CellSource:
    """Where a cell's value came from, precisely enough to go and look."""
    document: str                  # file name, or the reference workbook's name
    page: int | None = None        # 1-based; None for a structured source
    quote: str = ""                # the verbatim passage supporting the value
    method: str = ""               # how it was located: "search" | "structured" | "computed"
    field_name: str = ""

    def cite(self) -> str:
        page = f" p.{self.page}" if self.page else ""
        return f"{self.document}{page}"


@dataclass(frozen=True)
class StructuredSource:
    """A value read from a spreadsheet cell (XREF, Well List, Project Log).

    Not a document, but not "no source" either: it is re-readable, so a value
    citing it can be confirmed by looking the cell up again.
    """
    workbook: str
    sheet: str
    row: int
    column: str
    field_name: str = ""

    def cite(self) -> str:
        return f"{self.workbook}[{self.sheet}]!{self.column}{self.row}"


@dataclass
class ProvenanceStore:
    """(sheet, cell) -> CellSource. Internal only.

    NEVER a tab in the deliverable: the workbook's tab set must equal the
    template's. This rides in the sidecar next to the DDR.
    """
    entries: dict[tuple[str, str], CellSource] = field(default_factory=dict)

    def put(self, sheet: str, cell: str, source: CellSource) -> None:
        self.entries[(sheet, cell)] = source

    def get(self, sheet: str, cell: str) -> CellSource | None:
        return self.entries.get((sheet, cell))

    def audit_rows(self) -> list[tuple]:
        """Rows for DD_Audit_Trail: cell-level, citing document + page."""
        return [
            (sheet, cell, "document_page", source.cite(), 1.0,
             f"{source.field_name} @ {source.cite()} :: {source.quote[:120]}")
            for (sheet, cell), source in sorted(self.entries.items())
        ]

    def __len__(self) -> int:
        return len(self.entries)


def split_pages(text: str) -> list[str]:
    """OCR text -> pages. Both readers join with a form feed."""
    return (text or "").split("\f")


def _norm(text: str) -> str:
    return " ".join(_TOKEN_RE.findall(str(text).upper()))


def locate_page(text: str, quote: str, min_ratio: float = ANCHOR_MIN_RATIO) -> int | None:
    """The 1-based page whose text best supports *quote*, or None.

    Searches — it does not take the extractor's word for it.
    """
    anchor = locate_anchor(text, quote, min_ratio=min_ratio)
    return anchor.page if anchor else None


@dataclass(frozen=True)
class Anchor:
    """A passage in the source that supports a value, found by searching."""
    page: int
    quote: str
    ratio: float

    def cite(self) -> str:
        return f"p.{self.page}"


def locate_anchor(text: str, value: Any, min_ratio: float = ANCHOR_MIN_RATIO,
                  window: int = ANCHOR_WINDOW) -> Anchor | None:
    """Find the passage in *text* that best supports *value* — independently.

    Slides a window over each page and scores similarity against the value. The
    value may be a summary, so an exact match is not expected; what we need is
    the passage a human would point at. Below `min_ratio` we return None and the
    caller reports NO_ANCHOR: an anchor we are not confident in would let a wrong
    summary look proven, which is worse than admitting we could not find one.
    """
    needle_tokens = _content_tokens(value)
    if not needle_tokens:
        return None
    best: Anchor | None = None
    raw_pages = split_pages(text)
    for page_number, page in enumerate(raw_pages, start=1):
        words = page.split()
        if not words:
            continue
        # Slide a clause-sized window in WORDS and score by CONTAINMENT: what
        # share of the value's content words this passage actually contains.
        # Sequence similarity is the wrong metric here — a faithful summary is
        # a fraction of its source's length, so its ratio against the full
        # clause is low however true it is. Containment asks the question we
        # mean: "is what this says present here?"
        span = max(window // 6, 12)
        step = max(span // 3, 4)
        for start in range(0, max(len(words) - span, 0) + 1, step):
            chunk_words = words[start:start + span]
            chunk_tokens = _content_tokens(" ".join(chunk_words))
            if not chunk_tokens:
                continue
            score = len(needle_tokens & chunk_tokens) / len(needle_tokens)
            if score >= min_ratio and (best is None or score > best.ratio):
                # Score on the tight window (precision), but return a PADDED
                # quote (context). The completeness check asks what the source
                # says that the summary dropped, and a quote clipped at the
                # scoring boundary hides exactly that: the consent proviso
                # trailing the acreage caps sat one clause past the window, so
                # a real dropped term went unreported.
                pad = span
                lo, hi = max(0, start - pad), min(len(words), start + span + pad)
                best = Anchor(page=page_number,
                              quote=" ".join(words[lo:hi]), ratio=score)
    return best


# Words that carry no evidence: they appear in every clause of every instrument.
_STOPWORDS = {
    "THE", "A", "AN", "OF", "TO", "AND", "OR", "IN", "ON", "AT", "BY", "FOR",
    "WITH", "AS", "IS", "ARE", "BE", "SHALL", "MAY", "ANY", "ALL", "SUCH",
    "THIS", "THAT", "IT", "ITS", "FROM", "NOT", "NO", "PLUS", "PER", "UP",
    "HEREBY", "HEREIN", "THEREOF", "SAID", "OTHER", "THAN", "WHICH",
}


def _content_tokens(text: Any) -> set[str]:
    """The tokens that carry evidence: numbers, acreages, and real words."""
    return {t for t in _TOKEN_RE.findall(str(text).upper())
            if t not in _STOPWORDS and len(t) > 1}


def _window_of(raw_page: str, normalized_chunk: str, window: int) -> str:
    """A readable verbatim snippet from the raw page for the matched chunk."""
    head = normalized_chunk.split()[:6]
    if head:
        probe = re.escape(head[0])
        m = re.search(probe, raw_page, re.IGNORECASE)
        if m:
            start = max(0, m.start() - 40)
            return " ".join(raw_page[start:start + window].split())
    return " ".join(raw_page[:window].split())


def facts_in(text: Any) -> set[str]:
    """The factual tokens a value asserts: numbers, fractions, percentages.

    These are what a summary can get WRONG in a way that matters — an acreage
    cap, a percentage, a fraction. Words can be paraphrased; 40 acres cannot
    become 640 acres.
    """
    out: set[str] = set()
    for raw in _FACT_RE.findall(str(text)):
        token = re.sub(r"\s+", "", raw).rstrip(".")
        token = token.lstrip("0") or "0" if re.fullmatch(r"0+", token) else token
        out.add(token.upper())
    return out


def check_fidelity(summary: Any, anchor_text: str) -> set[str]:
    """Facts the summary asserts that its anchor does NOT contain.

    A non-empty result is a summary saying something its own source does not —
    hallucination — and it FAILS. Comparison is on normalized digits so "40" in
    "40 acres" matches "40 acres" however the OCR spaced it.
    """
    anchor_facts = facts_in(anchor_text)
    anchor_digits = re.sub(r"[^0-9/.%]", "", str(anchor_text))
    invented = set()
    for fact in facts_in(summary):
        if fact in anchor_facts:
            continue
        if re.sub(r"[^0-9/.%]", "", fact) and re.sub(r"[^0-9/.%]", "", fact) in anchor_digits:
            continue
        invented.add(fact)
    return invented


# Terms whose loss changes what the reader believes about the lease.
_MATERIAL_TERMS = (
    ("depth limitation", r"\bdepth\b"),
    ("Pugh clause", r"\bpugh\b"),
    ("consent requirement", r"\bwithout .{0,20}consent\b|\bconsent of lessor\b"),
    ("shut-in royalty", r"\bshut[- ]in\b"),
    ("horizontal well terms", r"\bhorizontal\b"),
    ("acreage tolerance", r"\btolerance\b"),
)


def check_completeness(summary: Any, anchor_text: str) -> list[str]:
    """Material terms present in the anchor but dropped from the summary.

    Not a failure — a summary is allowed to be shorter than its source. But a
    dropped depth limitation is the kind of omission that costs money, so it is
    surfaced for a human rather than lost silently.
    """
    summary_text = str(summary).lower()
    anchor_lower = str(anchor_text).lower()
    dropped = []
    for label, pattern in _MATERIAL_TERMS:
        if re.search(pattern, anchor_lower) and not re.search(pattern, summary_text):
            dropped.append(label)
    return dropped


# ---------------------------------------------------------------------------
# Provenance on write: find the document + page that actually backs each value
# ---------------------------------------------------------------------------

# Which sheet/column carries which kind of value, and where its backing document
# lives. This is the map from a written cell to the documents worth searching.
_OWN_FIELDS = {19: "MI Value", 20: "WI Value"}          # S, T -> controlling opinions
_OWN_RECORDING = (11, 12)                                # K, L -> the DPU Exhibit A


def populate_provenance(rows, source_index, *, controlling_docs=None,
                        dpu_recording_map=None, xref_name="Lease to Well XREF"):
    """Build a ProvenanceStore for the written rows, locating each page
    INDEPENDENTLY by searching the source — never trusting the extractor's cite.

    Returns (store, notes). A value found in a document is recorded with that
    document + page (and if that document differs from the one the pipeline
    thought, the note flags a miscitation — this is how the superseded-opinion
    "cited ORIG but the value is in SUPP" defect surfaces). A value that comes
    from the XREF is recorded as a StructuredSource — a real, re-readable
    citation, not a document and not "no source". A value found nowhere is left
    out; the truth checker reports it UNVERIFIABLE.
    """
    from src.dd.source_truth_check import _norm_key, normalize_for_match, value_variants

    store = ProvenanceStore()
    notes: list[str] = []
    controlling_docs = list(controlling_docs or [])

    def locate_in_docs(value, owner, field, claimed_doc=None):
        """(document_name, page) for the doc+page where the OWNER and the VALUE
        co-occur — searched independently.

        Owner-anchoring is not optional. A bare fraction like 1/36 or a decimal
        recurs across opinions, so searching for the value alone cites whichever
        document happens to contain that number — my first cut cited Kramer for a
        Cox owner exactly this way. Requiring the owner's name on the same page
        as the value makes the citation distinctive and correct, and it is the
        page a human would actually turn to.
        """
        owner_key = _norm_key(owner) if owner else ""
        best = None
        for name, text in controlling_docs:
            variants = [v for v in value_variants(value) if normalize_for_match(v)]
            for page_no, page in enumerate(split_pages(text), start=1):
                page_norm = normalize_for_match(page)
                if not any(normalize_for_match(v) in page_norm for v in variants):
                    continue
                # Owner must appear on the SAME page as the value.
                if owner_key and owner_key[:14] not in _norm_key(page):
                    continue
                match = next(v for v in variants if normalize_for_match(v) in page_norm)
                candidate = (name, page_no, match)
                if best is None:
                    best = candidate
                if claimed_doc and _norm_key(claimed_doc) in _norm_key(name):
                    return candidate           # claimed doc confirmed on this page
        return best

    for r in rows:
        row_no = r.get("_excel_row")
        if not row_no:
            continue
        # MI / WI -> the controlling opinion where THIS OWNER's value is stated.
        owner = r.get("lessor")
        for col, field in _OWN_FIELDS.items():
            value = r.get("mi_value" if col == 19 else "wi_value")
            if value is None:
                continue
            claimed = r.get("wi_source") or r.get("source_to_file_number") or r.get("source_lease_detail")
            located = locate_in_docs(value, owner, field, claimed)
            cell = f"{'S' if col == 19 else 'T'}{row_no}"
            if located:
                name, page, quote = located
                store.put("Ownership Report", cell,
                          CellSource(name, page, quote, "search", field))
                if claimed and _norm_key(str(claimed)) not in _norm_key(name):
                    notes.append(f"Ownership {cell}: {owner} value found in {name} p.{page}, "
                                 f"but the pipeline cited {claimed!r} — MISCITATION corrected.")
        # Record Book/Page -> the DPU, page located independently.
        if r.get("record_book") and dpu_recording_map is not None:
            store.put("Ownership Report", f"K{row_no}",
                      CellSource("DPU Exhibit A", None,
                                 f"Vol {r.get('record_book')}, Pg {r.get('record_page')}",
                                 "structured", "Record Book/Page"))
        # Lease no / lessor / lessee genuinely come from the XREF — a real,
        # re-readable citation, recorded as such rather than dressed up as a doc.
        for col, key, field in ((2, "lease_no", "Lease No."), (5, "lessor", "Lessor"),
                                (6, "lessee", "Lessee")):
            if r.get(key):
                store.put("Ownership Report", f"{chr(64+col)}{row_no}",
                          CellSource(xref_name, None, str(r.get(key)), "structured", field))
    return store, notes
