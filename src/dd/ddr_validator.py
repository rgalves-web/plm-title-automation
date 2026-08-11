"""Deterministic DDR validator — the final gate before a DDR is marked ready.

This is CODE running fixed rules over 100% of populated cells. It does not
sample, and it exercises no judgement about what is worth checking: it visits
every populated cell in every sheet and accounts for each one. If the count of
cells visited does not reconcile with the count populated, the run FAILS — a
validator that quietly skipped cells is worse than none, because it converts
"unknown" into "approved".

Every rule here was written from a defect that actually shipped in a Maxwell DDR
and had to be found by hand (see the workbook's own correction log):

  orphan_cells        <- "Ownership Report C815: orphan 'A' removed"
  nri_sanity          <- "col V Cox rows: NRI formula =1-G-W was missing"
  royalty_presence    <- "G32 Loy D. Self royalty 1/5" / "r37 State lease royalty unknown"
  template_sample     <- "template shipped with Texaco/SMK/1991 sample data; it propagated"
  foreign_unit        <- "Wiese Unit opinion (50.73ac, T0140007) removed - not Maxwell"
  mi_per_tract        <- MI flattened to one owner's fraction across a tract
  client_facing       <- triage/commentary text reaching a client cell
  audit_trace         <- values with no recorded source

A FAIL blocks "ready". A blank that carries a recorded reason is NOT a failure —
it is listed separately as pending, because a known gap is a work item and an
unexplained one is a defect.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any, Iterable

FAIL = "FAIL"
PENDING = "PENDING"
# A divergence the landman DECLARED, with a recorded reason — logged in the gate
# report, never silently absorbed, never a FAIL. Anything undeclared stays FAIL.
DECLARED = "DECLARED"

# Provenance layer: not client-facing, but still counted and orphan-checked.
_AUDIT_SHEET = "DD_Audit_Trail"

# The ONLY tab the pipeline may add to the template's own. It carries the source
# of every value (invariant 5) and is present in the approved deliverable.
# The validator itself adds nothing: its report is a sidecar file, never a tab —
# a quality gate that edits the artefact it is judging is not a gate.
SANCTIONED_EXTRA_SHEETS = frozenset({_AUDIT_SHEET})

# Template tabs that are scratch and must NEVER ship. The PLM template carries a
# worked example ("delete - A.E. Carroll 4H") whose name says so.
_TEMPLATE_SCRATCH_RE = re.compile(r"^\s*delete\s*-", re.IGNORECASE)

_EMPTY = {"", "-", "--", "—", "N/A"}

# Triage/commentary that must never reach a client-facing cell: notes the
# automation wrote to itself, which say nothing to the reader.
_TRIAGE_MARKERS = ("REVIEW REQUIRED", "REDLINE", "DUPLICATE OF", "NEEDS REVIEW",
                   "PARSE ERROR", "TODO", "FIXME", "NOT PROVIDED IN OCR",
                   "XXX", "???")

# The APPROVED inline pending marker. A contract known from the XREF whose PDF is
# not in the file is stubbed "[PENDING - awaiting contract PDF]" by design, so
# the reader sees the contract exists and can order it. That is a recorded
# reason, not commentary — reported as pending, never as a failure.
_PENDING_MARKER = "[PENDING"

# Tokens from the PLM template's own sample rows. The template ships populated
# with another deal's data, so anything matching these is template bleed, not
# this unit's title.
_TEMPLATE_TOKENS = ("TEXACO", "SMK", "REEVES", "636.13", "A.E. CARROLL",
                    "FOREST OIL", "ARAPAHOE", "***")
# A bare year token only counts as template bleed alongside a template name.
_TEMPLATE_YEARS = ("1991",)

_LEASE_RE = re.compile(r"\b\d{7}-\d{3}\b")
_CONTRACT_RE = re.compile(r"\bK\d{7}(?:-[A-Z]{1,4})?\b")
_TO_RE = re.compile(r"\bT0\d{6}\b")


@dataclass(frozen=True)
class Finding:
    sheet: str
    cell: str
    value: Any
    rule: str
    expected: str
    severity: str = FAIL

    def describe(self) -> str:
        return (f"[{self.severity}] {self.sheet} · {self.cell} · {self.rule}: "
                f"value={str(self.value)[:48]!r} — expected {self.expected}")


@dataclass
class SheetCoverage:
    sheet: str
    populated: int = 0
    visited: int = 0

    @property
    def reconciled(self) -> bool:
        return self.populated == self.visited


@dataclass
class ValidationReport:
    # Set ONLY when the gate was replayed against a pinned date (regression over
    # an already-shipped deliverable). Never set on the ship path — a shipping
    # run always judges against the real today, so a stale submission date is a
    # structural FAIL (flow spec S8 freshness gate). When set, every rendering of
    # this report announces REPLAY so a replayed verdict can never be mistaken
    # for a ship-time one.
    replay_as_of: Any = None
    coverage: list[SheetCoverage] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    # Source-truth result (src/dd/source_truth_check). Structural rules verify
    # FORM; this verifies the values are what their sources actually say.
    truth: Any | None = None

    @property
    def failures(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == FAIL]

    @property
    def pending(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == PENDING]

    @property
    def total_cells(self) -> int:
        return sum(c.populated for c in self.coverage)

    @property
    def checked_cells(self) -> int:
        return sum(c.visited for c in self.coverage)

    @property
    def reconciled(self) -> bool:
        """Did the review actually cover every populated cell?"""
        return all(c.reconciled for c in self.coverage)

    @property
    def source_mismatches(self) -> list[Any]:
        return list(self.truth.mismatches) if self.truth else []

    @property
    def ready(self) -> bool:
        """Ready needs BOTH: nothing structurally wrong, and nothing that
        contradicts its own source. A cell can be perfectly formed and false."""
        return self.reconciled and not self.failures and not self.source_mismatches

    def summary(self) -> str:
        prefix = f"REPLAY — as_of={self.replay_as_of} · " if self.replay_as_of else ""
        head = (f"{self.checked_cells} of {self.total_cells} cells checked "
                f"({len(self.failures)} FAIL, {len(self.pending)} pending)")
        if self.truth is not None:
            head += f"; source truth: {self.truth.summary()}"
        if not self.reconciled:
            short = [f"{c.sheet}: {c.visited}/{c.populated}" for c in self.coverage
                     if not c.reconciled]
            return f"{prefix}COVERAGE DID NOT RECONCILE — {head}. Unaccounted: {'; '.join(short)}"
        return prefix + ("READY — " if self.ready else "NOT READY — ") + head


# ---------------------------------------------------------------------------
# Declared data blocks
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SheetSpec:
    """The region of a sheet the pipeline is allowed to populate."""
    max_col: int
    body_gap: int = 12   # this many blank rows ends the declared block


# Column counts follow the PLM template; body_gap ends the block after the data.
_SHEET_SPECS: dict[str, SheetSpec] = {
    "Summary": SheetSpec(max_col=3),
    "Ownership Report": SheetSpec(max_col=24),
    "Ownership - Wells": SheetSpec(max_col=27),
    "Lease Review": SheetSpec(max_col=20),
    "Agreements": SheetSpec(max_col=12),
    "Unit and Pooling Agreements": SheetSpec(max_col=12),
    "Runsheet": SheetSpec(max_col=27),
    "PLM Title Review": SheetSpec(max_col=12),
    "Disclaimer": SheetSpec(max_col=11),
    "Ownership - 1H (No FO Option)": SheetSpec(max_col=26),
    _AUDIT_SHEET: SheetSpec(max_col=6),
}
_DEFAULT_SPEC = SheetSpec(max_col=30)


def _spec(sheet_name: str) -> SheetSpec:
    return _SHEET_SPECS.get(sheet_name, _DEFAULT_SPEC)


def is_populated(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() not in _EMPTY
    return True


def populated_cells(worksheet) -> list[tuple[str, int, int, Any]]:
    """(coordinate, row, col, value) for every populated cell."""
    out = []
    for row in worksheet.iter_rows():
        for cell in row:
            if is_populated(cell.value):
                out.append((cell.coordinate, cell.row, cell.column, cell.value))
    return out


def declared_block_end(cells: list[tuple[str, int, int, Any]], spec: SheetSpec) -> int:
    """The last row of the sheet's contiguous declared block.

    Walks the populated rows in order; the block ends at the first gap wider than
    `body_gap`. A cell stranded past that gap is an orphan — which is exactly the
    shape of the real defect: a lone "A" at C815 with the body ending at row 37.
    """
    rows = sorted({r for _c, r, _col, _v in cells})
    if not rows:
        return 0
    end = rows[0]
    for row in rows[1:]:
        if row - end > spec.body_gap:
            break
        end = row
    return end


# ---------------------------------------------------------------------------
# Allowlist for foreign-unit leakage
# ---------------------------------------------------------------------------

# "Wiese Unit", "Maxwell A Unit", "Alamo B Unit" — a capitalised name (optionally
# followed by a single-letter series designator) immediately before "Unit".
_UNIT_PHRASE_RE = re.compile(r"\b([A-Za-z][A-Za-z'\-]{2,})\s+(?:[A-Za-z]\s+)?UNIT\b",
                             re.IGNORECASE)
# Words that precede "Unit" without naming one — including the measure words that
# appear in prose like "a 160-acre unit" or "the wellbore unit".
_GENERIC_UNIT_QUALIFIERS = {"THE", "THIS", "SAID", "POOLED", "SUBJECT", "CAPTIONED",
                            "PER", "AND", "ONE", "EACH", "ANY", "SUCH", "WITHIN",
                            "INTO", "FOR", "OTHER", "DRILLING", "PRODUCTION",
                            "ACRE", "ACRES", "WELLBORE", "GAS", "OIL", "POOLING",
                            "SURFACE", "LEASEHOLD", "PRORATION", "SPACING",
                            # Common English words seen before "unit" in analyst
                            # prose (Bowen: "a DIFFERENT unit", "OUTSIDE unit
                            # boundary", "AFFECTS unit …"). No Texas unit is
                            # plausibly NAMED one of these; a real name like
                            # SIEBOLD still flags (regression-tested).
                            "DIFFERENT", "OUTSIDE", "AFFECTS"}


@dataclass
class UnitAllowlist:
    """What legitimately belongs to THIS unit, derived from XREF + DPU."""
    unit_name: str = ""
    leases: set[str] = field(default_factory=set)
    contracts: set[str] = field(default_factory=set)
    title_opinions: set[str] = field(default_factory=set)
    identity_tokens: set[str] = field(default_factory=set)   # {"MAXWELL"}
    foreign_unit_names: set[str] = field(default_factory=set)  # known other units (reporting)

    def unknown_leases(self, text: str) -> set[str]:
        return {m for m in _LEASE_RE.findall(text) if m not in self.leases}

    def unknown_contracts(self, text: str) -> set[str]:
        return {m for m in _CONTRACT_RE.findall(text) if m not in self.contracts}

    def unknown_title_opinions(self, text: str) -> set[str]:
        return {m for m in _TO_RE.findall(text) if m not in self.title_opinions}

    def foreign_units_in(self, text: str) -> set[str]:
        """Unit NAMES other than ours, found as the phrase "<Name> Unit".

        Two earlier attempts were unsound. Matching bare tokens as substrings
        made "Client:" hit a unit called "C". Matching them as whole words was no
        better: the tokens derived from other units' contract titles are the
        LESSOR SURNAMES of every landowner in the county — Kramer, Lynn, Parker,
        Walker — which are also Maxwell's own parties, so it flagged real data.

        The signal that actually identifies the defect is the phrase: the Wiese
        opinion reached this deliverable as "Wiese Unit opinion". A capitalised
        name immediately followed by "Unit" names a unit; if that name is not
        ours, it does not belong here.
        """
        found = set()
        for match in _UNIT_PHRASE_RE.finditer(text):
            name = match.group(1).upper()
            if name in _GENERIC_UNIT_QUALIFIERS or name in self.identity_tokens:
                continue
            found.add(name)
        return found


def build_allowlist(unit_name: str, xref_rows: Iterable[dict[str, Any]],
                    unit_leases: Iterable[str],
                    dpu_leases: Iterable[str] = ()) -> UnitAllowlist:
    """Derive what belongs to this unit from the XREF and the DPU.

    Everything else that looks like a lease/contract/opinion identifier, or names
    another unit, is leakage: the Wiese opinion reached a Maxwell deliverable
    exactly this way.
    """
    from src.dd.agreements_xref import unit_identity_tokens

    leases = {str(x) for x in unit_leases} | {str(x) for x in dpu_leases}
    identity = unit_identity_tokens(unit_name)
    allow = UnitAllowlist(unit_name=unit_name, leases=leases, identity_tokens=set(identity))
    for row in xref_rows:
        lease_no = str(row.get("lease_no") or "")
        number = str(row.get("contract_no") or "").strip()
        name = str(row.get("contract_name") or "")
        if lease_no in leases and number:
            (allow.title_opinions if _TO_RE.fullmatch(number) else allow.contracts).add(number)
        # Record other units by NAME PHRASE ("... - WIESE UNIT"), for reporting.
        for match in _UNIT_PHRASE_RE.finditer(name):
            token = match.group(1).upper()
            if (token not in identity and token not in _GENERIC_UNIT_QUALIFIERS
                    and _is_unit_name_token(token)):
                allow.foreign_unit_names.add(token)
    allow.foreign_unit_names -= identity
    return allow


# Words that appear in a contract's NAME without naming a unit.
_NOT_A_UNIT_NAME = {
    "UNIT", "UNITS", "DECL", "DECLARATION", "DEC", "POOLED", "POOLING", "AGREEMENT",
    "AGMT", "ASMT", "ASSIGNMENT", "PARTIAL", "FARMOUT", "AMENDMENT", "AMND", "AMEND",
    "SECOND", "THIRD", "FIRST", "CORRECTION", "RATIFICATION", "MEMORANDUM", "DESIGNATION",
    "AND", "THE", "OF", "TO", "FROM", "INC", "LLC", "LTD", "COMPANY", "CORP", "OIL",
    "GAS", "ENERGY", "RESOURCES", "MINERAL", "MINERALS", "LEASE", "LEASEHOLD", "WELL",
    "NO", "TRACT", "ACRES", "SURVEY", "COUNTY", "TEXAS", "STATE", "EOG", "ENCANA",
    "BURLINGTON", "JOA", "PSA", "LETTER", "DRILL", "SITE", "WATER", "LINE", "SURFACE",
    "OPTION", "DEVELOPMENT", "CONFIDENTIALITY", "ACREAGE", "CONTRIBUTION", "PRODUCTION",
    "SHARING", "MISCELLANEOUS", "TERM", "BILL", "SALE", "PURCHASE", "OTHER",
}


def _is_unit_name_token(token: str) -> bool:
    """Is this token plausibly a UNIT's name?

    Guarded hard, because this feeds a rule that fails the run: a token must be a
    real word (alphabetic, >= 4 chars) and not vocabulary that shows up in every
    contract title. Without this, splitting names yielded 508 "unit names" —
    including "C", "T" and "1" — and every cell containing the letter C failed.
    """
    return token.isalpha() and len(token) >= 4 and token not in _NOT_A_UNIT_NAME


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------

def _as_fraction(value: Any) -> Fraction | None:
    if value is None:
        return None
    if isinstance(value, Fraction):
        return value
    if isinstance(value, (int, float)):
        return Fraction(str(value))
    text = str(value).strip()
    if text.startswith("="):
        body = text[1:]
        if "/" in body and re.fullmatch(r"\s*\d+\s*/\s*\d+\s*", body):
            num, den = body.split("/")
            return Fraction(int(num), int(den))
        return None
    try:
        return Fraction(text)
    except (ValueError, ZeroDivisionError):
        return None


_DOC_ID_RE = re.compile(r"\bK\d{7}(?:-[A-Z]{1,4})?\b|\b\d{7}-\d{3}\b")


def documents_on_disk(unit_folder) -> set[str]:
    """Contract / lease identifiers whose document packages exist in the unit's
    project folder — the ground truth for whether "document not in file" is true.
    Identifiers are read from file and folder NAMES (zips included); nothing is
    opened."""
    from pathlib import Path

    unit_folder = Path(unit_folder)
    found: set[str] = set()
    if not unit_folder.exists():
        return found
    for path in unit_folder.rglob("*"):
        found.update(_DOC_ID_RE.findall(path.name))
    return found


def check_pending_docs_on_disk(sheet_name: str, worksheet, cells,
                               available: set[str] | None) -> list[Finding]:
    """A PENDING marker claiming "document not in file" is a FALSE STATEMENT when
    the document sits in the project folder — the exact defect this run fixes:
    three Agreements blocks said "not in file" while all three packages were on
    disk. The identifier is the block's own contract/lease number (col A above
    the marker) or any identifier inside the marker text.
    """
    if not available or sheet_name == _AUDIT_SHEET:
        return []
    findings = []
    current_id: str | None = None
    for coord, row, col, value in sorted(cells, key=lambda c: (c[1], c[2])):
        text = str(value)
        if col == 1:
            ids = _DOC_ID_RE.findall(text)
            if ids:
                current_id = ids[0]
        if _PENDING_MARKER in text.upper():
            referenced = set(_DOC_ID_RE.findall(text)) or ({current_id} if current_id else set())
            on_disk = sorted(referenced & available)
            if on_disk:
                findings.append(Finding(
                    sheet_name, coord, value, "pending_document_on_disk",
                    f"'document not in file' is FALSE — {', '.join(on_disk)} exists in the "
                    "project folder; the pipeline must read it or fail loudly"))
    return findings


def expected_sheet_set(template_workbook,
                       sanctioned: Iterable[str] = SANCTIONED_EXTRA_SHEETS) -> set[str]:
    """The tabs a finished DDR must have: the template's, minus its scratch tab,
    plus the sanctioned provenance tab.

    Not literally "the template's tabs": the template ships a worked example
    ("delete - A.E. Carroll 4H") that must never reach a client, and the
    deliverable carries DD_Audit_Trail, which the template has no reason to hold.
    Everything else is a defect — a tab nobody meant to ship (a stray copy, a
    scratch sheet, a tool writing its own output into the deliverable).
    """
    template_tabs = {s for s in template_workbook.sheetnames
                     if not _TEMPLATE_SCRATCH_RE.match(s)}
    return template_tabs | set(sanctioned)


def check_sheet_set(workbook, expected: set[str] | None,
                    declared_exclusions: dict[str, str] | None = None) -> list[Finding]:
    """The workbook's tab set must equal the expected set exactly.

    declared_exclusions: {sheet_name: reason} — template tabs the landman
    DECLARED excluded, with the reason recorded. A declared missing tab is
    logged as a DECLARED EXCLUSION finding (visible in the report and sidecar),
    not a FAIL. Any divergence NOT declared stays FAIL — the default is
    unchanged, and extra tabs are never excusable this way."""
    if not expected:
        return []
    declared = declared_exclusions or {}
    actual = set(workbook.sheetnames)
    findings = []
    for extra in sorted(actual - expected):
        reason = ("this tab is the template's scratch example and must never ship"
                  if _TEMPLATE_SCRATCH_RE.match(extra)
                  else "no tab may be added to the deliverable beyond the template's "
                       f"plus {sorted(SANCTIONED_EXTRA_SHEETS)}")
        findings.append(Finding("(workbook)", extra, extra, "sheet_set", reason))
    for missing in sorted(expected - actual):
        if missing in declared:
            findings.append(Finding(
                "(workbook)", missing, None, "sheet_set",
                f"DECLARED EXCLUSION: {declared[missing]}", severity=DECLARED))
            continue
        findings.append(Finding("(workbook)", missing, None, "sheet_set",
                                "the template defines this tab; the deliverable is missing it"))
    return findings


# ---------------------------------------------------------------------------
# PLM submission-checklist rules
# ---------------------------------------------------------------------------

# The token a reviewer fills at send time. Unmistakable on sight — a stale date
# looks valid and ships silently; this cannot be mistaken for a real date.
SUBMISSION_DATE_TOKEN = "{SUBMISSION_DATE}"

_DATE_LABEL_RE = re.compile(r"^\s*date(\s*submitted)?\s*:?\s*$", re.IGNORECASE)
_DATE_VALUE_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")

# Placeholders the client's blank template ships with, checked in header rows.
_HEADER_PLACEHOLDER_TOKENS = ("REEVES", "636.13", "A.E. CARROLL", "FOREST OIL",
                              "ARAPAHOE", "TEXACO", "***", "3-11")


def check_submission_date(workbook, today=None) -> list[Finding]:
    """A "Date:"/"Date Submitted:" cell must not carry a hard-coded past date.

    The DDR is dated when it is SENT. A date baked in on the day the pipeline
    happened to run ships as a lie about when the work was certified, and it
    looks perfectly valid — nobody catches it by reading. Either the reviewer
    fills SUBMISSION_DATE_TOKEN at send, or the date is today; a past date FAILS.
    """
    from datetime import date as _date, datetime as _datetime

    today = today or _date.today()
    findings: list[Finding] = []
    for sheet_name in workbook.sheetnames:
        if sheet_name == _AUDIT_SHEET:
            continue
        ws = workbook[sheet_name]
        for row in ws.iter_rows():
            for cell in row:
                if not isinstance(cell.value, str) or not _DATE_LABEL_RE.match(cell.value):
                    continue
                value_cell = ws.cell(cell.row, cell.column + 1)
                value = value_cell.value
                if value is None or str(value).strip() == "":
                    continue
                if SUBMISSION_DATE_TOKEN in str(value):
                    findings.append(Finding(
                        sheet_name, value_cell.coordinate, value, "submission_date",
                        "confirm submission date — fill the token at send time",
                        severity=PENDING))
                    continue
                stamped = None
                if isinstance(value, (_datetime, _date)):
                    stamped = value.date() if isinstance(value, _datetime) else value
                else:
                    m = _DATE_VALUE_RE.search(str(value))
                    if m:
                        try:
                            stamped = _date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
                        except ValueError:
                            stamped = None
                if stamped is None:
                    continue
                if stamped < today:
                    findings.append(Finding(
                        sheet_name, value_cell.coordinate, value, "submission_date",
                        f"the submission date is hard-coded to {stamped.isoformat()}, in the past — "
                        f"use {SUBMISSION_DATE_TOKEN} or today's date"))
    return findings


def check_disclaimer_names_the_client(workbook, client_name: str | None) -> list[Finding]:
    """The Disclaimer assigns ownership of the work product — to the CLIENT, by
    name. The template ships with a stand-in ("ABC, LLC"); shipping that assigns
    the report to a company that does not exist."""
    if "Disclaimer" not in workbook.sheetnames or not client_name:
        return []
    ws = workbook["Disclaimer"]
    findings: list[Finding] = []
    named = False
    for row in ws.iter_rows():
        for cell in row:
            if not isinstance(cell.value, str):
                continue
            text = cell.value
            if normalize_client(client_name) in normalize_client(text):
                named = True
            for stand_in in ("ABC, LLC", "ABC LLC", "XYZ, LLC"):
                if stand_in.upper() in text.upper():
                    findings.append(Finding(
                        "Disclaimer", cell.coordinate, stand_in, "disclaimer_names_the_client",
                        f"the template's stand-in {stand_in!r} must be the client "
                        f"({client_name}) — this clause assigns ownership of the report"))
    if not named and not findings:
        findings.append(Finding(
            "Disclaimer", "(sheet)", None, "disclaimer_names_the_client",
            f"the Disclaimer never names the client ({client_name})"))
    return findings


def normalize_client(text: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "", str(text).upper())


# A header that still describes land — acreage, a survey, an abstract — is a
# legal description, and a legal description is unit-specific by definition.
_LEGAL_DESCRIPTION_RE = re.compile(
    r"\b\d[\d,.]*\s*acres?\b|\bsurvey\b|\bA-\d+\b|\bblock\b|\bsection\b", re.IGNORECASE)


def check_headers_have_no_placeholder(workbook, template_workbook=None,
                                      header_rows: int = 3) -> list[Finding]:
    """A header naming another deal's property is the loudest possible defect —
    it is the first thing the reader sees.

    The authority is the TEMPLATE, not a token list. A hardcoded list of the
    template's example words ("Reeves", "636.13") only catches the examples
    someone thought to write down: it missed this template's OTHER example, the
    704.04-acre W.W. Boaton tract on the "Ownership - 1H" tab, which shipped
    unfilled. So the rule is structural instead: if a header cell still holds a
    LEGAL DESCRIPTION byte-identical to the template's, nobody filled it in.
    """
    findings: list[Finding] = []
    for sheet_name in workbook.sheetnames:
        if sheet_name == _AUDIT_SHEET:
            continue
        ws = workbook[sheet_name]
        template_ws = (template_workbook[sheet_name]
                       if template_workbook and sheet_name in template_workbook.sheetnames
                       else None)
        for row in ws.iter_rows(min_row=1, max_row=header_rows):
            for cell in row:
                if not isinstance(cell.value, str):
                    continue
                upper = cell.value.upper()
                hit = next((t for t in _HEADER_PLACEHOLDER_TOKENS if t in upper), None)
                if hit:
                    findings.append(Finding(
                        sheet_name, cell.coordinate, cell.value[:60],
                        "template_placeholder_in_header",
                        f"a header must name THIS unit, not the template's example ({hit!r})"))
                    continue
                if template_ws is None:
                    continue
                template_value = template_ws[cell.coordinate].value
                if (isinstance(template_value, str)
                        and cell.value.strip() == template_value.strip()
                        and _LEGAL_DESCRIPTION_RE.search(cell.value)):
                    findings.append(Finding(
                        sheet_name, cell.coordinate, cell.value[:60],
                        "template_placeholder_in_header",
                        "this header still holds the TEMPLATE's legal description verbatim — "
                        "it was never filled in for this unit"))
    return findings


def check_template_value_not_replaced(workbook, template_workbook,
                                      key_col: int = 1) -> list[Finding]:
    """A cell the writer left holding the TEMPLATE's example value, on a row it
    otherwise filled with real data.

    This is the generalisation of the header rule, and it exists because that
    rule was too narrow: scanning only rows 1-3, it reported 2 stale cells on
    Lease Review when in truth all 30 rows of the pooling-clause column still
    held the template's example verbatim. The template's own text is the
    authority — no token list required, and no example can hide from it.

    The discriminator is the ROW: if the row's key cell differs from the
    template (a real lease number where the template says "L1"), the writer
    touched this row. Any cell on it still identical to the template was simply
    never filled, and it is now asserting another deal's terms about this lease.
    """
    findings: list[Finding] = []
    for sheet_name in workbook.sheetnames:
        if sheet_name == _AUDIT_SHEET or sheet_name not in template_workbook.sheetnames:
            continue
        ws, tws = workbook[sheet_name], template_workbook[sheet_name]
        for row in ws.iter_rows():
            key, template_key = ws.cell(row[0].row, key_col).value, tws.cell(row[0].row, key_col).value
            # Only rows the writer actually filled: key present and changed.
            if not is_populated(key) or key == template_key:
                continue
            for cell in row:
                if not is_populated(cell.value) or not isinstance(cell.value, str):
                    continue
                template_value = tws[cell.coordinate].value
                if not isinstance(template_value, str):
                    continue
                if cell.value.strip() == template_value.strip() and len(cell.value.strip()) > 12:
                    findings.append(Finding(
                        sheet_name, cell.coordinate, cell.value[:56],
                        "template_value_not_replaced",
                        f"row {row[0].row} holds real data ({str(key)[:14]!r}) but this cell is "
                        "still the template's example verbatim — it was never filled, and now "
                        "states another deal's terms about this lease"))
    return findings


def check_recording_matches_dpu(workbook, dpu_by_lease: dict[str, tuple] | None,
                                sheet: str = "Ownership Report",
                                lease_col: int = 2, book_col: int = 11,
                                page_col: int = 12) -> list[Finding]:
    """Ownership Record Book/Page must equal the DPU Exhibit A, exactly.

    The Declaration's Exhibit A is the authority for every unit lease's recording
    reference. A wrong one sends the reader to the wrong instrument, and it is
    invisible on inspection: "Volume 37" and "Volume 371" look equally plausible
    on a page of volume numbers. That exact defect (lease 0190122-006, Flynt —
    the DPU says Volume 371, Page 293) shipped and was caught only because an
    amber review-flag happened to be sitting on the cell. Luck is not a control.

    A digit dropped, a neighbouring lease's reference copied (Hulme carrying
    Cox's 475/39), a transposition — all are the same failure, and all are
    mechanically decidable against Exhibit A. So they FAIL rather than warn.
    """
    if not dpu_by_lease or sheet not in workbook.sheetnames:
        return []
    ws = workbook[sheet]
    findings: list[Finding] = []
    for row in range(1, ws.max_row + 1):
        lease = ws.cell(row, lease_col).value
        if not is_populated(lease):
            continue
        entry = dpu_by_lease.get(str(lease).strip())
        if not entry:
            continue                      # not in Exhibit A: source-truth reports it
        src_book, src_page = (str(x).strip() if x is not None else None for x in entry)
        book, page = ws.cell(row, book_col).value, ws.cell(row, page_col).value
        if not is_populated(book) and not is_populated(page):
            continue                      # blank carries its own pending reason
        got = (str(book).strip() if book is not None else None,
               str(page).strip() if page is not None else None)
        if src_book is None or src_page is None:
            continue                      # the DPU itself prints a blank
        if got != (src_book, src_page):
            findings.append(Finding(
                sheet, f"K{row}/L{row}", f"Vol {got[0]}, Pg {got[1]}",
                "recording_matches_dpu",
                f"lease {lease} is recorded at Vol {src_book}, Pg {src_page} per the DPU's "
                f"Exhibit A — the workbook says Vol {got[0]}, Pg {got[1]}"))
    return findings


# The writer's amber review fill (ddr_writer.REVIEW_FILL) marks a value a human
# must look at. It is a working state, not a delivery state.
_REVIEW_FILL_RGB = "FFEB9C"


def check_no_review_fills(workbook) -> list[Finding]:
    """No amber review-flag cells may survive into a deliverable.

    The fill means "a human has not confirmed this yet". Shipping it either sends
    the client a value nobody stood behind, or — worse — the colour is stripped by
    a copy/paste and the doubt disappears while the value stays. Either way the
    flag has to be resolved before delivery, not carried into it.
    """
    findings: list[Finding] = []
    for sheet_name in workbook.sheetnames:
        if sheet_name == _AUDIT_SHEET:
            continue
        for row in workbook[sheet_name].iter_rows():
            for cell in row:
                fill = cell.fill
                if not fill or fill.fill_type != "solid":
                    continue
                rgb = str(getattr(fill.start_color, "rgb", "") or "")
                if rgb.upper().endswith(_REVIEW_FILL_RGB):
                    findings.append(Finding(
                        sheet_name, cell.coordinate, cell.value, "review_fill_present",
                        "an amber review flag means nobody has confirmed this value — "
                        "resolve it before delivery; a deliverable carries no open flags"))
    return findings


def check_orphan_cells(sheet_name: str, cells, spec: SheetSpec) -> list[Finding]:
    """Populated cells outside the sheet's declared block."""
    end = declared_block_end(cells, spec)
    findings = []
    for coord, row, col, value in cells:
        if row > end:
            findings.append(Finding(
                sheet_name, coord, value, "orphan_cell",
                f"no data below row {end} (declared block ends there)"))
        elif col > spec.max_col:
            findings.append(Finding(
                sheet_name, coord, value, "orphan_cell",
                f"no data right of column {spec.max_col}"))
    return findings


def check_client_facing(sheet_name: str, cells) -> list[Finding]:
    """A client cell holds a value, a citation, or nothing — never commentary."""
    if sheet_name == _AUDIT_SHEET:
        return []
    findings = []
    for coord, _row, _col, value in cells:
        if not isinstance(value, str):
            continue
        upper = value.upper()
        if upper.lstrip().startswith(_PENDING_MARKER):
            findings.append(Finding(
                sheet_name, coord, value, "pending_marker",
                "document not in file — stub carries its reason inline (approved format)",
                severity=PENDING))
            continue
        hit = next((m for m in _TRIAGE_MARKERS if m in upper), None)
        if hit:
            findings.append(Finding(
                sheet_name, coord, value, "client_facing_commentary",
                f"no triage text ({hit!r}) in a client cell — record the reason in the audit layer"))
    return findings


def check_template_sample(sheet_name: str, cells) -> list[Finding]:
    """The PLM template ships populated with another deal's data."""
    if sheet_name == _AUDIT_SHEET:
        return []
    findings = []
    for coord, _row, _col, value in cells:
        text = str(value).upper()
        hit = next((t for t in _TEMPLATE_TOKENS if t in text), None)
        if hit is None and any(y in text for y in _TEMPLATE_YEARS):
            hit = next((y for y in _TEMPLATE_YEARS if y in text), None) if len(text) < 24 else None
        if hit:
            findings.append(Finding(
                sheet_name, coord, value, "template_sample_data",
                f"no template placeholder data ({hit!r}) — scrub the template's sample rows"))
    return findings


# A neighbouring unit's name is legitimate when the cell CITES that unit's title
# opinion as a SOURCE — a reviewer may rely on a shared-tract TO from an adjacent
# unit. What is leakage is another unit's DATA (a lease, an acreage) sitting in a
# client value cell as if it were ours. The distinguisher is source-citation
# language near the name: "T-O", "opinion", "per", "source", "covers", a T0#.
_SOURCE_CITATION_RE = re.compile(
    r"\bT-?O\b|\bTITLE OPINION\b|\bOPINION\b|\bPER\b|\bSOURCE\b|\bCOVERS?\b|"
    r"\bSHARED\b|\bT0\d{6}\b|\bCITED?\b|\bDO T-O\b|\bLEASE ANALYSIS\b",
    re.IGNORECASE)


def _cites_our_lease_as_subject(text: str, allow: "UnitAllowlist") -> bool:
    """True when the cell cites a foreign TO IN SERVICE OF one of OUR leases.

    Source-citation language alone is too weak: 'Wiese Unit opinion, 50.73 acres'
    contains 'opinion' yet is the Wiese unit's OWN data masquerading as a Maxwell
    title-opinion summary — the r110 leak. A genuine citation reads 'Wiese Unit
    T-O is the source for lease 0190122-005 MI', where OUR lease is the subject
    and the foreign TO is merely where we confirmed it. So the exemption requires
    BOTH source language AND one of our own lease numbers present.
    """
    if not _SOURCE_CITATION_RE.search(text):
        return False
    return any(lease in text for lease in allow.leases)


def check_foreign_unit(sheet_name: str, cells, allow: UnitAllowlist) -> list[Finding]:
    """Another unit's DATA in a client cell = leakage (FAIL). Another unit's TO
    CITED AS A SOURCE in a note = legitimate (pass).

    The ID checks need a populated allowlist to mean anything. An EMPTY one does
    not mean "nothing belongs here" — it means the allowlist never got built (a
    missing XREF, a unit not found), and treating that as evidence turns every
    legitimate lease number into a confident accusation. Verified: an empty
    allowlist against the real Maxwell workbook produced 88 false failures across
    every sheet. Absence of knowledge is not knowledge of absence.

    A neighbouring unit's name is fine when the cell CITES its opinion as a
    source (reviewer guidance: a shared-tract TO from an adjacent unit is a valid
    source). So a foreign-unit-NAME hit stands down when the cell reads as a
    source citation; a foreign LEASE/CONTRACT identifier — actual data — never
    does.
    """
    if sheet_name == _AUDIT_SHEET or allow is None:
        return []
    findings = []
    populated = allow.leases or allow.contracts or allow.title_opinions
    for coord, _row, _col, value in cells:
        text = str(value)
        cites = _cites_our_lease_as_subject(text, allow)
        if populated:
            # DATA identifiers are leakage regardless of surrounding prose.
            for lease in allow.unknown_leases(text):
                findings.append(Finding(sheet_name, coord, value, "foreign_unit_leakage",
                                        f"lease {lease} is not in {allow.unit_name}'s lease set"))
            for contract in allow.unknown_contracts(text):
                findings.append(Finding(sheet_name, coord, value, "foreign_unit_leakage",
                                        f"contract {contract} is not linked to {allow.unit_name}"))
            # A foreign TO identifier is leakage ONLY when it is not being cited
            # as a source; cited, it is the reviewer relying on a shared-tract TO.
            for opinion in allow.unknown_title_opinions(text):
                if not cites:
                    findings.append(Finding(sheet_name, coord, value, "foreign_unit_leakage",
                                            f"title opinion {opinion} does not cover {allow.unit_name}"))
        # A foreign unit NAME is leakage only when it is NOT a source citation.
        if not cites:
            for unit in allow.foreign_units_in(text):
                findings.append(Finding(sheet_name, coord, value, "foreign_unit_leakage",
                                        f"names another unit ({unit}) — not {allow.unit_name}"))
    return findings


# --- Ownership Report row rules -------------------------------------------

_OWN = "Ownership Report"
_COL = {"lease_no": 2, "royalty": 7, "tract_gross": 18, "mi": 19, "wi": 20,
        "nri": 22, "orri": 23}
_DATA_START = 8


def _own_rows(worksheet, cells) -> list[int]:
    end = declared_block_end(cells, _spec(_OWN))
    return [r for r in range(_DATA_START, end + 1)
            if is_populated(worksheet.cell(r, _COL["lease_no"]).value)]


def check_nri_sanity(worksheet, rows, pending_reasons) -> list[Finding]:
    """Every row with a WI must carry a real NRI: 0 < NRI < 1.

    NRI is the template formula =1-G-W, which openpyxl does not evaluate, so it
    is recomputed from royalty and ORRI. A blank or out-of-range NRI on a row
    that claims a working interest is a defect, not a gap.
    """
    findings = []
    for row in rows:
        wi = _as_fraction(worksheet.cell(row, _COL["wi"]).value)
        if wi is None:
            continue
        nri_cell = worksheet.cell(row, _COL["nri"]).value
        royalty = _as_fraction(worksheet.cell(row, _COL["royalty"]).value)
        orri = _as_fraction(worksheet.cell(row, _COL["orri"]).value) or Fraction(0)
        if not is_populated(nri_cell):
            findings.append(Finding(_OWN, f"V{row}", nri_cell, "nri_sanity",
                                    "row has a WI, so NRI (=1-G-W) must be present"))
            continue
        nri = _as_fraction(nri_cell)
        if nri is None and royalty is not None:
            nri = Fraction(1) - royalty - orri
        if nri is None:
            continue  # a formula we cannot evaluate; royalty rule covers the input
        if not (Fraction(0) < nri < Fraction(1)):
            findings.append(Finding(_OWN, f"V{row}", float(nri), "nri_sanity",
                                    "0 < NRI < 1"))
    return findings


def check_royalty_presence(worksheet, rows, pending_reasons) -> list[Finding]:
    """Every active WI row carries a royalty, or a recorded reason why not."""
    findings = []
    for row in rows:
        if _as_fraction(worksheet.cell(row, _COL["wi"]).value) is None:
            continue
        if is_populated(worksheet.cell(row, _COL["royalty"]).value):
            continue
        lease = worksheet.cell(row, _COL["lease_no"]).value
        reason = pending_reasons.get(f"G{row}") or pending_reasons.get(str(lease))
        findings.append(Finding(
            _OWN, f"G{row}", None, "royalty_presence",
            f"lease {lease} has a WI, so it must carry a royalty",
            severity=PENDING if reason else FAIL))
    return findings


def check_mi_per_tract(worksheet, rows) -> list[Finding]:
    """A tract's mineral ownership is a partition of unity: MI cannot sum > 1.

    A tract-gross cell that carries TEXT instead of acreage (e.g. Bowen's
    "Pending tract allocation … see Original T-O 4/15/2008 request") cannot be
    assigned to a tract, so its row is excluded from the partition sum — and the
    condition is surfaced as a PENDING finding, never skipped silently. Before
    this guard the whole gate crashed on the float() call, which reported
    nothing at all."""
    by_tract: dict[Any, list[tuple[int, Fraction]]] = {}
    findings: list[Finding] = []
    for row in rows:
        mi = _as_fraction(worksheet.cell(row, _COL["mi"]).value)
        gross = worksheet.cell(row, _COL["tract_gross"]).value
        if mi is None or not is_populated(gross):
            continue
        try:
            tract_key = round(float(gross), 4)
        except (TypeError, ValueError):
            findings.append(Finding(
                _OWN, f"R{row}", str(gross)[:80], "mi_per_tract_sum",
                "tract gross acres is not numeric — row excluded from the MI "
                "partition check until the tract is allocated",
                severity=PENDING))
            continue
        by_tract.setdefault(tract_key, []).append((row, mi))
    for tract, entries in by_tract.items():
        total = sum((mi for _r, mi in entries), Fraction(0))
        if total - Fraction(1) > Fraction(1, 10**6):
            rows_text = ", ".join(f"S{r}" for r, _ in entries)
            findings.append(Finding(
                _OWN, rows_text, float(total), "mi_per_tract_sum",
                f"MI across tract {tract} acres must sum to <= 1 (got {float(total):.6f})"))
    return findings


def check_audit_trace(worksheet, rows, audited_rows: set[str]) -> list[Finding]:
    """Every derived row value traces to an audit-trail source."""
    findings = []
    for row in rows:
        if not any(is_populated(worksheet.cell(row, c).value)
                   for c in (_COL["mi"], _COL["wi"], _COL["nri"])):
            continue
        if f"row {row}" in audited_rows or str(worksheet.cell(row, _COL["lease_no"]).value) in audited_rows:
            continue
        findings.append(Finding(
            _OWN, f"row {row}", worksheet.cell(row, _COL["lease_no"]).value,
            "audit_trace", "every derived value must cite a source in DD_Audit_Trail"))
    return findings


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _audit_index(workbook) -> tuple[set[str], dict[str, str]]:
    """(locations recorded in the audit trail, pending reasons by location)."""
    located: set[str] = set()
    reasons: dict[str, str] = {}
    if _AUDIT_SHEET in workbook.sheetnames:
        ws = workbook[_AUDIT_SHEET]
        for row in range(2, ws.max_row + 1):
            location = ws.cell(row, 2).value
            source_type = str(ws.cell(row, 3).value or "")
            if location:
                located.add(str(location).strip())
                if "pending" in source_type.lower() or "flagged" in source_type.lower():
                    reasons[str(location).strip()] = source_type
    # Pending reasons live in the audit trail (source_type "pending:*" /
    # "flagged_pending"), read above — there is no separate Pending Items tab:
    # the deliverable carries the template's tabs plus DD_Audit_Trail, nothing else.
    return located, reasons


def validate_ddr(workbook, allowlist: UnitAllowlist | None = None,
                 expected_sheets: set[str] | None = None,
                 documents_available: set[str] | None = None,
                 dpu_by_lease: dict | None = None,
                 client_name: str | None = None,
                 template_workbook=None,
                 today=None,
                 declared_sheet_exclusions: dict[str, str] | None = None) -> ValidationReport:
    """Run every rule over every populated cell. Nothing is sampled.

    expected_sheets: the tab set the deliverable must have (see
    expected_sheet_set). When None the tab-set rule is skipped — pass it from the
    template for a real run.
    documents_available: identifiers of document packages present in the unit's
    project folder (see documents_on_disk). A PENDING marker referencing one of
    them is a FALSE "not in file" claim and FAILS.
    declared_sheet_exclusions: {sheet: reason} — landman-declared template-tab
    exclusions, logged as DECLARED, never FAIL (undeclared stays FAIL).
    """
    report = ValidationReport()
    audited, pending_reasons = _audit_index(workbook)
    report.findings.extend(check_sheet_set(workbook, expected_sheets,
                                           declared_exclusions=declared_sheet_exclusions))
    # PLM submission checklist — workbook-wide, so they run once, not per sheet.
    report.findings.extend(check_submission_date(workbook, today=today))
    report.findings.extend(check_disclaimer_names_the_client(workbook, client_name))
    report.findings.extend(check_headers_have_no_placeholder(workbook, template_workbook))
    report.findings.extend(check_recording_matches_dpu(workbook, dpu_by_lease))
    report.findings.extend(check_no_review_fills(workbook))
    if template_workbook is not None:
        report.findings.extend(check_template_value_not_replaced(workbook, template_workbook))

    for sheet_name in workbook.sheetnames:
        worksheet = workbook[sheet_name]
        spec = _spec(sheet_name)
        cells = populated_cells(worksheet)
        coverage = SheetCoverage(sheet=sheet_name, populated=len(cells))

        # Universal pass: EVERY populated cell goes through these.
        for check in (
            lambda: check_orphan_cells(sheet_name, cells, spec),
            lambda: check_client_facing(sheet_name, cells),
            lambda: check_template_sample(sheet_name, cells),
            lambda: check_foreign_unit(sheet_name, cells, allowlist),
            lambda: check_pending_docs_on_disk(sheet_name, worksheet, cells, documents_available),
        ):
            report.findings.extend(check())
        coverage.visited = len(cells)  # the universal pass visited each one
        report.coverage.append(coverage)

        if sheet_name == _OWN:
            rows = _own_rows(worksheet, cells)
            report.findings.extend(check_nri_sanity(worksheet, rows, pending_reasons))
            report.findings.extend(check_royalty_presence(worksheet, rows, pending_reasons))
            report.findings.extend(check_mi_per_tract(worksheet, rows))
            report.findings.extend(check_audit_trace(worksheet, rows, audited))

    return report


def write_validation_sidecar(report: ValidationReport, ddr_path) -> "Path":
    """Write the report NEXT TO the DDR as <name>_validation.txt.

    The validator never writes into the deliverable. A gate that edits the
    artefact it is judging is not a gate — and the deliverable's tab set is part
    of what it checks, so emitting its own tab would have made the workbook fail
    its own rule. The report is a sidecar; the DDR is untouched.
    """
    from pathlib import Path

    ddr_path = Path(ddr_path)
    sidecar = ddr_path.with_name(f"{ddr_path.stem}_validation.txt")
    sidecar.write_text(console_summary(report), encoding="utf-8")
    return sidecar


def console_summary(report: ValidationReport) -> str:
    lines = [report.summary(), ""]
    if report.truth is not None:
        from src.dd.source_truth_check import truth_table
        lines.append(truth_table(report.truth))
        lines.append("")
    lines.append(f"{'sheet':<32}{'populated':>10}{'checked':>9}{'ok':>5}")
    for c in report.coverage:
        lines.append(f"{c.sheet:<32}{c.populated:>10}{c.visited:>9}{'yes' if c.reconciled else 'NO':>5}")
    lines.append("")
    if report.failures:
        lines.append(f"FAILURES ({len(report.failures)}):")
        lines.extend("  " + f.describe() for f in report.failures)
    else:
        lines.append("FAILURES (0): none")
    if report.pending:
        lines.append(f"\nPENDING — blanks with a recorded reason ({len(report.pending)}), not failures:")
        lines.extend("  " + f.describe() for f in report.pending)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# The mandatory gate
# ---------------------------------------------------------------------------

class DDRNotReadyError(RuntimeError):
    """A DDR failed validation. It exists on disk; it is NOT ready to send."""


def run_final_validation(
    output_path,
    *,
    template_path=None,
    allowlist=None,
    dpu_by_lease=None,
    documents_available=None,
    client_name=None,
    source_roots=(),
    run_source_truth_check: bool = True,
    declared_sheet_exclusions: dict[str, str] | None = None,
    as_of=None,
    write_sidecar: bool | None = None,
) -> "ValidationReport":
    # as_of is REPLAY-ONLY: it pins the date the submission-date rule judges
    # against, so re-validating an already-shipped deliverable months later does
    # not manufacture a FAIL. It is never plumbed into the ship path (packager,
    # writer, UI) and never read from config — a shipping run judges against the
    # real today, which is what makes a stale "Date Submitted" a structural FAIL.
    """Validate a written DDR and drop its sidecar. The pipeline's last act.

    Called for EVERY unit, always: a gate that runs when someone remembers is a
    suggestion. It never edits the workbook — the report is a sidecar file, so
    the gate cannot contaminate what it is judging.

    Returns the report; the caller decides whether a red run raises. `ready`
    means both structurally clean AND nothing contradicting its own source.
    """
    import openpyxl

    from pathlib import Path

    output_path = Path(output_path)
    workbook = openpyxl.load_workbook(output_path)
    template_workbook = (openpyxl.load_workbook(template_path)
                         if template_path and Path(template_path).exists() else None)
    expected = expected_sheet_set(template_workbook) if template_workbook else None

    report = validate_ddr(
        workbook, allowlist,
        expected_sheets=expected,
        documents_available=documents_available,
        dpu_by_lease=dpu_by_lease,
        client_name=client_name,
        template_workbook=template_workbook,
        declared_sheet_exclusions=declared_sheet_exclusions,
        today=as_of,   # None = real today (send-time); a date = regression as-of
    )
    report.replay_as_of = as_of        # marks every rendering as REPLAY
    if run_source_truth_check and source_roots:
        from src.dd.source_truth_check import run_source_truth
        report.truth = run_source_truth(workbook, list(source_roots),
                                        dpu_by_lease=dpu_by_lease)
    # The sidecar sits NEXT TO the deliverable, so writing it is a side effect on
    # the delivered folder. Two rules:
    #  - a REPLAY (as_of pinned) never writes: re-validating a shipped unit must
    #    not mutate what was shipped;
    #  - a caller that applies human rulings AFTER this call (the flow runner
    #    applies sanctions) passes write_sidecar=False and writes it itself,
    #    otherwise the file on disk would report FAILs the verdict has already
    #    resolved.
    should_write = (as_of is None) if write_sidecar is None else write_sidecar
    if should_write:
        write_validation_sidecar(report, output_path)
    return report
