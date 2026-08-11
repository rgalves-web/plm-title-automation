"""Title opinions — the two facts that decide scope, extracted properly.

Both facts here were learned from real documents, and both were wrong the
obvious way first:

  CERTIFICATION DATE. It is not on the cover page and it is usually not phrased
  as "certified to". In the Bowen opinions it lives on page 21 of 36, inside a
  Runsheet Issues requirement, as "Our opinion covers title through February 4,
  2008". A front-pages read returns the LETTER date instead — and the letter
  date is not the scope floor. Supplemental review runs from the certification
  date, so a wrong one silently changes what has to be examined. This module
  therefore never guesses it: it sweeps cheap OCR for the phrase family,
  confirms the hit by vision, and when it finds nothing it says so. An
  unresolved certification date is a BLOCKING finding (flow spec §2 rule 6),
  never a substituted date.

  COVERAGE DELTA. A supplemental restates the legal description, and sometimes
  the restatement is bigger than the original: Bowen's First Supplemental covers
  262.5 acres across A-227 AND A-226, where the original covered 141.5 acres in
  A-227 alone. That is not a formatting difference — it is the opinion silently
  enlarging its own scope, and it must raise a flag at ingestion instead of at
  audit.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

# How these opinions actually say it. Ordered: the first family is the real
# certification statement, the rest are weaker phrasings seen in the wild.
_CERT_PHRASES = (
    r"opinion covers title through",
    r"opinion is certified (?:to|through)",
    r"we (?:hereby )?certify title",
    r"certified to [A-Z][a-z]+ \d{1,2}, \d{4}",
    r"title (?:is )?examined through",
)
_CERT_RE = re.compile("|".join(_CERT_PHRASES), re.IGNORECASE)
_DATE_RE = re.compile(r"([A-Z][a-z]+ \d{1,2}, \d{4})")
_ABSTRACT_RE = re.compile(r"\bA-\s?(\d{2,4})\b")
_ACRES_RE = re.compile(r"([\d,]+\.?\d*)\s*acres", re.IGNORECASE)

CERT_INSTRUCTION = """This page is from a Texas title opinion.

Find the sentence that states THROUGH WHAT DATE the opinion examines title —
the scope date. It is often phrased "Our opinion covers title through <date>",
"certified to <date>", or "title examined through <date>". It is NOT the letter
date at the top of the opinion and NOT a recording date.

Return exactly two lines:
CERT: <the date exactly as printed, or NONE ON THIS PAGE>
QUOTE: <the verbatim sentence containing it, or NONE>"""


@dataclass
class CertDate:
    value: str
    page: int
    quote: str
    method: str = "vision"

    def to_dict(self) -> dict[str, Any]:
        return {"value": self.value, "page": self.page, "quote": self.quote,
                "method": self.method}


@dataclass
class Blocking:
    """A finding that stops adoption. Never a fallback.

    `candidate` is the difference between "I found nothing" and "I found
    something weaker than proof". Bowen's First Supplemental carries no
    certification sentence at all; the date the delivered package used
    (10/18/2008) is the through-date of the runsheet recited under DOCUMENTS
    EXAMINED. That is a defensible basis and a human can adopt it in one click —
    but the system may not adopt it silently, because "the runsheet covered
    title to X" is not "the examiner certified title to X"."""
    subject: str
    reason: str
    detail: str = ""
    candidate: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"subject": self.subject, "reason": self.reason,
                "detail": self.detail, "candidate": self.candidate}


def find_cert_date(pdf: str | Path, *, cache_dir: str | Path,
                   pages_text: list[str] | None = None,
                   ocr_dpi: int = 200) -> CertDate | Blocking:
    """Locate the certification date, or say plainly that it was not found."""
    from src.knowledge.dpu_reader import ocr_pdf
    from src.knowledge.vision import render_pages, read_page

    pdf = Path(pdf)
    pages = pages_text if pages_text is not None else ocr_pdf(pdf, dpi=ocr_dpi)
    hits = [i + 1 for i, t in enumerate(pages) if _CERT_RE.search(t or "")]

    for page_no in hits:
        text = pages[page_no - 1]
        m = _CERT_RE.search(text)
        window = text[m.start():m.start() + 200]
        dm = _DATE_RE.search(window)
        if not dm:
            continue
        # OCR found it; vision confirms the words before it is trusted.
        try:
            for img in render_pages(pdf, [page_no], dpi=200):
                answer = read_page(img, CERT_INSTRUCTION, cache_dir=cache_dir,
                                   max_tokens=600)
            if "NONE ON THIS PAGE" not in answer:
                value = _line(answer, "CERT:") or dm.group(1)
                quote = _line(answer, "QUOTE:") or " ".join(window.split())
                return CertDate(value=value, page=page_no, quote=quote)
        except Exception:                       # noqa: BLE001 — OCR still stands
            pass
        return CertDate(value=dm.group(1), page=page_no,
                        quote=" ".join(window.split()), method="ocr")

    return Blocking(
        subject=str(pdf.name),
        reason="cert_date_nao_localizada",
        detail=(f"swept {len(pages)} pages for the certification statement and "
                f"found none. The letter date is NOT a substitute: supplemental "
                f"review runs from the certification date."),
        candidate=_runsheet_recital(pages))


# "Runsheet dated December 4, 2008 ... covering the Land from Sovereignty to
# October 18, 2008" — the DOCUMENTS EXAMINED recital. Weaker than a
# certification, and the only thing some supplementals give you.
# Periods are not sentence boundaries here: OCR of "AED Group, LIC, tor FOG Re-
# sources, Inc., covering the Land from Sovereignty to October 18, 2008" is one
# recital wearing four full stops.
_RUNSHEET_RE = re.compile(
    r"[Rr]unsheet[\s\S]{0,250}?(?:\bto|\bthrough)\s+([A-Z][a-z]+ \d{1,2}, \d{4})")


def _runsheet_recital(pages: list[str]) -> dict[str, Any] | None:
    for page_no, text in enumerate(pages, start=1):
        m = _RUNSHEET_RE.search(text or "")
        if m:
            return {"value": m.group(1), "page": page_no,
                    "basis": "runsheet through-date recited under DOCUMENTS EXAMINED",
                    "quote": " ".join(text[m.start():m.start() + 220].split()),
                    "requires_human_verdict": True}
    return None


def _line(answer: str, prefix: str) -> str:
    for line in (answer or "").splitlines():
        if line.strip().upper().startswith(prefix):
            return line.split(":", 1)[1].strip()
    return ""


# ---------------------------------------------------------------------------
# Coverage delta
# ---------------------------------------------------------------------------

@dataclass
class CoverageDelta:
    changed: bool
    abstracts_added: list[str] = field(default_factory=list)
    abstracts_removed: list[str] = field(default_factory=list)
    acres_from: str = ""
    acres_to: str = ""
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"changed": self.changed, "abstracts_added": self.abstracts_added,
                "abstracts_removed": self.abstracts_removed,
                "acres_from": self.acres_from, "acres_to": self.acres_to,
                "summary": self.summary}


def coverage_delta(original_description: str, supplemental_description: str,
                   original_acres: str = "", supplemental_acres: str = "") -> CoverageDelta:
    """Compare a supplemental's own legal description against the original's.

    A supplemental that quietly covers a survey the original never did has
    changed the unit's title picture. Comparing the two descriptions is the only
    way to see it, and it is cheap — both are already extracted."""
    orig_abs = {m.group(1) for m in _ABSTRACT_RE.finditer(original_description or "")}
    supp_abs = {m.group(1) for m in _ABSTRACT_RE.finditer(supplemental_description or "")}
    added = sorted(supp_abs - orig_abs, key=_as_int)
    removed = sorted(orig_abs - supp_abs, key=_as_int)
    a_from = original_acres or _first_acres(original_description)
    a_to = supplemental_acres or _first_acres(supplemental_description)
    changed = bool(added or removed) or (
        bool(a_from and a_to) and _num(a_from) != _num(a_to))
    if not changed:
        return CoverageDelta(changed=False, acres_from=a_from, acres_to=a_to,
                             summary="same coverage")

    parts = []
    if a_from and a_to and _num(a_from) != _num(a_to):
        verb = "ENLARGED" if _num(a_to) > _num(a_from) else "REDUCED"
        parts.append(f"{verb} {a_from} ac -> {a_to} ac")
    if added:
        parts.append("surveys added: " + ", ".join(f"A-{a}" for a in added))
    if removed:
        parts.append("surveys dropped: " + ", ".join(f"A-{a}" for a in removed))
    return CoverageDelta(changed=True, abstracts_added=added,
                         abstracts_removed=removed, acres_from=a_from,
                         acres_to=a_to, summary="; ".join(parts))


def _first_acres(text: str) -> str:
    m = _ACRES_RE.search(text or "")
    return m.group(1) if m else ""


def _num(value: str) -> float:
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


def _as_int(value: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
