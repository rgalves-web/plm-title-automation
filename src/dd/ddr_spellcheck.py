"""Spell-check pass over a DDR's text cells (PLM checklist item 11).

REPORTS, never corrects. A title deliverable is dense with things a dictionary
does not know and must not touch: surnames (Brumbaugh, Croxton, Hrabovsky),
legal terms of art (lessor, pooled, ratification), abbreviations (ORRI, DSU,
NRI), instrument identifiers and survey references. Auto-correcting any of them
would silently corrupt the record — the exact failure mode this project spends
its effort preventing. So the pass produces a list for a human to read.

What is deliberately NOT reported:
  * capitalised words — a proper noun, and there is no dictionary of Montague
    County landowners;
  * anything in the domain vocabulary below;
  * identifiers, numbers, and anything containing a digit or punctuation;
  * words that appear in the workbook's own source documents (if a term is in
    the title opinion, the DDR spelling it the same way is correct by
    definition, whatever a dictionary thinks).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

# Terms of art, abbreviations and units that a general dictionary lacks. Not a
# spelling authority — a list of words it is not this tool's business to judge.
DOMAIN_VOCABULARY = {
    # interests / instruments
    "orri", "nri", "wi", "mi", "npri", "dsu", "psa", "joa", "dpu", "dou", "xref",
    "lessor", "lessee", "lessors", "lessees", "leasehold", "leaseholds",
    "pooled", "pooling", "unitized", "unitization", "unitize", "farmout",
    "assignor", "assignee", "ratification", "ratified", "runsheet", "runsheets",
    "curative", "encumbrances", "hydrocarbons", "casinghead", "shut", "pugh",
    "wellbore", "wellbores", "recoupment", "nonconsent", "overriding",
    "reservations", "severance", "abstracted", "abstract", "acreage", "acres",
    "mineral", "minerals", "royalty", "royalties", "grantor", "grantee",
    "commencement", "reassignment", "unleased", "undivided", "prorata",
    # report / process
    "aov", "plm", "eog", "bkv", "rrc", "api", "ocr", "tif", "pdf",
    "certification", "supplemental", "confirmatory", "landman", "landmen",
    # geography / survey
    "montague", "calhoun", "texas", "survey", "league", "blk", "vol", "pg",
    "cursory", "examiner", "deed", "plat", "plats", "plots",
    # Flagged on the first real pass and confirmed legitimate, not misspellings:
    # Latin used in leases ("per annum"), standard abbreviations, and a word the
    # dictionary simply lacks. Recorded here so the report stays worth reading —
    # a spell check that cries wolf gets ignored, and then it catches nothing.
    "annum", "cert", "incl", "misattributed", "ac",
}

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z']{2,}")
_AUDIT_SHEET = "DD_Audit_Trail"


@dataclass(frozen=True)
class Misspelling:
    sheet: str
    cell: str
    word: str
    suggestion: str | None
    context: str

    def describe(self) -> str:
        hint = f" (did you mean {self.suggestion!r}?)" if self.suggestion else ""
        return f"{self.sheet} · {self.cell}: {self.word!r}{hint} — {self.context}"


def _candidate_words(text: str) -> list[str]:
    """Lower-case words worth judging: no proper nouns, no identifiers."""
    out = []
    for match in _WORD_RE.finditer(text):
        word = match.group(0)
        if word[0].isupper():
            continue                       # proper noun — not ours to judge
        if any(ch.isdigit() for ch in word):
            continue
        out.append(word.lower())
    return out


def spell_check_workbook(workbook, extra_vocabulary: Iterable[str] = (),
                         source_text: str = "") -> list[Misspelling]:
    """Every text cell in every client-facing sheet. Reports, never corrects."""
    try:
        from spellchecker import SpellChecker
    except ImportError:  # pragma: no cover - reported, never silently skipped
        raise RuntimeError(
            "pyspellchecker is not installed; item 11 cannot run. Install it or "
            "record the spell-check pass as not performed — never report it as clean.")

    checker = SpellChecker()
    known = {w.lower() for w in DOMAIN_VOCABULARY}
    known |= {w.lower() for w in extra_vocabulary}
    # A word the source documents use is correct here by definition.
    known |= {w.lower() for w in _WORD_RE.findall(source_text or "")}

    seen: set[tuple[str, str]] = set()
    findings: list[Misspelling] = []
    for sheet_name in workbook.sheetnames:
        if sheet_name == _AUDIT_SHEET:
            continue
        for row in workbook[sheet_name].iter_rows():
            for cell in row:
                if not isinstance(cell.value, str):
                    continue
                words = [w for w in _candidate_words(cell.value) if w not in known]
                if not words:
                    continue
                for word in checker.unknown(words):
                    key = (sheet_name, word)
                    if key in seen:
                        continue
                    seen.add(key)
                    findings.append(Misspelling(
                        sheet=sheet_name, cell=cell.coordinate, word=word,
                        suggestion=checker.correction(word),
                        context=_context(cell.value, word)))
    return findings


def _context(text: str, word: str) -> str:
    m = re.search(re.escape(word), text, re.IGNORECASE)
    if not m:
        return text[:60]
    start = max(0, m.start() - 30)
    return "…" + " ".join(text[start:m.end() + 30].split()) + "…"


def spellcheck_report(findings: list[Misspelling]) -> str:
    if not findings:
        return "SPELL CHECK: no unrecognised words outside proper nouns and domain vocabulary."
    lines = [f"SPELL CHECK — {len(findings)} word(s) for review "
             "(reported, NOT auto-corrected; proper nouns and legal terms excluded):"]
    lines.extend("  " + f.describe() for f in findings)
    return "\n".join(lines)
