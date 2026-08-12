"""The Runsheet — supplemental chain of title, in the house style.

It is the piece that unlocks the rest of the kit: Title Documents is not a
separate hunt, it is *whatever the runsheet lists*, named `book.page`. So a kit
with one title document and a missing runsheet is one hole, not two.

What enters is narrow and the narrowness is the product (see
`knowledge/rules/runsheet_style.yaml`): of record, recorded after the
controlling certification date, touching the Seller's interest or a unit tract.
Everything else stays visible in the ledger and out of the deliverable — the
unrecorded-memo leak that once polluted a delivered runsheet is a filter, not a
habit.

Three dates, never collapsed (Trevor's explicit requirement). They differ, and
which one differs is itself a finding.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

NOT_SHOWN = "not shown on copy"

# Categories that can be an instrument in the chain. A category outside this set
# is not "probably fine" — it is not an instrument.
CHAIN_CATEGORIES = frozenset({
    "lease_ogl", "lease_memorandum", "assignment", "deed_release_lien",
    "probate_heirship", "dpu", "dpu_amendment", "agreement",
})

INSTRUMENT_LABEL = {
    "lease_ogl": "Oil and Gas Lease",
    "lease_memorandum": "Memorandum of Oil and Gas Lease",
    "assignment": "Assignment",
    "deed_release_lien": "Deed",
    "probate_heirship": "Probate / Affidavit of Heirship",
    "dpu": "Declaration of Pooled Unit",
    "dpu_amendment": "Amendment to Declaration of Pooled Unit",
    "agreement": "Agreement",
}

_DATE_FORMATS = ("%B %d, %Y", "%m/%d/%Y", "%Y-%m-%d", "%d %B %Y")


def parse_date(value: Any) -> date | None:
    text = " ".join(str(value or "").split())
    if not text:
        return None
    m = re.search(r"[A-Z][a-z]+ \d{1,2}, \d{4}|\d{1,2}/\d{1,2}/\d{4}|\d{4}-\d{2}-\d{2}",
                  text)
    if not m:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(m.group(0), fmt).date()
        except ValueError:
            continue
    return None


@dataclass
class RunsheetEntry:
    no: int
    instrument: str
    instrument_number: str          # Vol/Pg (+ instrument no. when printed)
    effective_date: str
    instrument_date: str
    recorded_date: str
    grantor: str
    grantee: str
    acreage: str = ""
    conveyance: str = ""            # ONE sentence
    reservation: str = ""           # ONE sentence, omitted when nothing reserved
    source_file: str = ""
    source_page: Any = None
    needs_verdict: bool = True
    findings: list[str] = field(default_factory=list)

    def citation(self) -> str:
        page = f" p.{self.source_page}" if self.source_page else ""
        return f"{Path(str(self.source_file)).name}{page}"

    def to_dict(self) -> dict[str, Any]:
        return {"no": self.no, "instrument": self.instrument,
                "instrument_number": self.instrument_number,
                "effective_date": self.effective_date,
                "instrument_date": self.instrument_date,
                "recorded_date": self.recorded_date,
                "grantor": self.grantor, "grantee": self.grantee,
                "acreage": self.acreage, "conveyance": self.conveyance,
                "reservation": self.reservation, "cited_to": self.citation(),
                "needs_verdict": self.needs_verdict, "findings": self.findings}


# ---------------------------------------------------------------------------
# The filter
# ---------------------------------------------------------------------------

@dataclass
class Excluded:
    file: str
    reason: str
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"file": self.file, "reason": self.reason, "detail": self.detail}


def select(documents: list[dict[str, Any]], *, cert_date: date,
           seller: str = "EOG",
           of_record_by_file: dict[str, bool] | None = None,
           outside_files: set[str] | None = None
           ) -> tuple[list[dict[str, Any]], list[Excluded]]:
    """Which documents belong in the supplemental chain — and why the rest do not.

    Every exclusion is recorded with a reason from the closed vocabulary. A
    silently dropped instrument is the failure this function exists to prevent."""
    kept: list[dict[str, Any]] = []
    dropped: list[Excluded] = []
    for doc in documents:
        name = str(doc.get("file", ""))
        category = str(doc.get("classified_as") or "")
        # The perimeter filter belongs here too. An instrument over land the
        # unit never took is a real, recorded, post-cert instrument — and it
        # still has no business in this unit's chain of title.
        if name in (outside_files or set()):
            dropped.append(Excluded(name, "fora_do_perimetro",
                                    "the lease it belongs to contributes zero "
                                    "acres to the unit"))
            continue
        if category not in CHAIN_CATEGORIES:
            dropped.append(Excluded(name, "fora_do_tipo",
                                    f"classified {category}; not an instrument"))
            continue
        # Being of record is a property of the INSTRUMENT, not of the page that
        # happened to be scanned (see term_source._of_record_enough). A lease
        # whose first page shows no file stamp is still recorded when Exhibit
        # "A" gives its volume and page. `not_recorded` still never passes.
        status = str((doc.get("of_record") or {}).get("status") or "unknown")
        known = (of_record_by_file or {}).get(str(doc.get("file", "")), False)
        if status == "not_recorded" or (status != "recorded" and not known):
            dropped.append(Excluded(
                name, "nao_de_registro",
                "only an instrument OF RECORD enters the runsheet"))
            continue
        extracted = doc.get("extracted") or {}
        when = (parse_date(extracted.get("recorded_date"))
                or parse_date(extracted.get("instrument_date")))
        if when is None:
            dropped.append(Excluded(name, "nao_computavel",
                                    "no date could be read, so its position in "
                                    "the chain cannot be decided"))
            continue
        if when <= cert_date:
            dropped.append(Excluded(
                name, "pre_cert_date",
                f"of record {when.isoformat()}, at or before the controlling "
                f"certification date {cert_date.isoformat()}"))
            continue
        blob = " ".join(str(v) for v in extracted.values())
        if seller.lower() not in blob.lower():
            dropped.append(Excluded(name, "nao_adverso_a_eog",
                                    f"does not name {seller} and no unit tract "
                                    f"link was established"))
            continue
        kept.append(doc)
    return kept, dropped


# ---------------------------------------------------------------------------
# The house style
# ---------------------------------------------------------------------------

def _portion(text: str) -> str:
    m = re.search(r"\b(all|an undivided [^,.;]{1,40}|\d+/\d+|\d+(?:\.\d+)?%)\b",
                  str(text or ""), re.IGNORECASE)
    return m.group(1) if m else ""


def conveyance_sentence(instrument: str, grantor: str, grantee: str,
                        portion: str, where: str) -> str:
    """ONE sentence: what moved, from whom to whom, with the portion."""
    what = {"Oil and Gas Lease": "leased",
            "Memorandum of Oil and Gas Lease": "leased",
            "Assignment": "assigned",
            "Deed": "conveyed",
            "Declaration of Pooled Unit": "pooled",
            "Amendment to Declaration of Pooled Unit": "amended the pooling of",
            }.get(instrument, "conveyed")
    bits = [grantor or "Grantor"]
    bits.append(what)
    bits.append(portion or "its interest")
    if where:
        bits.append(f"in {where}")
    bits.append(f"to {grantee or 'Grantee'}")
    return " ".join(bits).strip().rstrip(".") + "."


_RESERVATION_RE = re.compile(
    r"\b(reserv\w+|except\w+|save and except)\b[^.;]{0,160}", re.IGNORECASE)


def reservation_sentence(text: str, grantor: str) -> str:
    """ONE sentence, or nothing at all. Never the word "none" in a cell."""
    m = _RESERVATION_RE.search(str(text or ""))
    if not m:
        return ""
    clause = " ".join(m.group(0).split()).rstrip(".,;")
    return f"{grantor or 'Grantor'} reserved {clause}.".replace("reserved reserv",
                                                               "reserved")


@dataclass
class Basis:
    """What the run was made FROM, declared in the tab like the hand runsheet
    declares it in its own A3. A runsheet whose floor is a guess is worse than
    no runsheet: every exclusion below it is unjustified."""
    cert_date: date
    confirmed: bool
    statement: str

    def to_dict(self) -> dict[str, Any]:
        return {"cert_date": self.cert_date.isoformat(),
                "confirmed": self.confirmed, "statement": self.statement}


def build(documents: list[dict[str, Any]], *, cert_date: date,
          unit_tracts: dict[str, str] | None = None,
          basis: "Basis | None" = None,
          of_record_by_file: dict[str, bool] | None = None,
          outside_files: set[str] | None = None
          ) -> tuple[list[RunsheetEntry], list[Excluded]]:
    kept, dropped = select(documents, cert_date=cert_date,
                           of_record_by_file=of_record_by_file,
                           outside_files=outside_files)

    def sort_key(doc: dict[str, Any]):
        e = doc.get("extracted") or {}
        return (parse_date(e.get("recorded_date"))
                or parse_date(e.get("instrument_date")) or date(1, 1, 1))

    entries: list[RunsheetEntry] = []
    for n, doc in enumerate(sorted(kept, key=sort_key), start=1):
        e = doc.get("extracted") or {}
        category = str(doc.get("classified_as"))
        label = INSTRUMENT_LABEL.get(category, "Instrument")
        grantor = str(e.get("grantor") or e.get("lessor") or "")
        grantee = str(e.get("grantee") or e.get("lessee") or "")
        portion = _portion(e.get("interest_covered") or e.get("legal_description"))
        where = str(e.get("unit_tract") or (unit_tracts or {}).get(
            str(e.get("recording")), "") or "")
        entry = RunsheetEntry(
            no=n, instrument=label,
            instrument_number=str(e.get("recording") or ""),
            effective_date=str(e.get("effective_date")
                               or e.get("instrument_date") or NOT_SHOWN),
            instrument_date=str(e.get("instrument_date") or NOT_SHOWN),
            recorded_date=str(e.get("recorded_date") or NOT_SHOWN),
            grantor=grantor, grantee=grantee, acreage=where,
            conveyance=conveyance_sentence(label, grantor, grantee, portion, where),
            reservation=reservation_sentence(e.get("legal_description", ""), grantor),
            source_file=str(doc.get("file", "")),
            source_page=(doc.get("evidence") or {}).get("page"))
        # A date that is present but disagrees with its neighbours is a finding,
        # not a tidy-up: an instrument recorded years after it was made changes
        # who had notice of what.
        made, filed = parse_date(entry.instrument_date), parse_date(entry.recorded_date)
        if made and filed and (filed - made).days > 365:
            entry.findings.append(
                f"recorded {(filed - made).days} days after execution — check "
                f"whether an intervening purchaser took without notice")
        if basis is not None and not basis.confirmed:
            entry.findings.append(
                "PROVISIONAL: the governing certification date is not confirmed "
                "— this entry's inclusion depends on it")
        entries.append(entry)
    return entries, dropped


def title_document_names(entries: list[RunsheetEntry]) -> list[str]:
    """Title Documents is not a separate hunt: it is the runsheet, named
    `book.page` per the PLM spec."""
    out: list[str] = []
    for e in entries:
        digits = re.findall(r"\d+", e.instrument_number)
        if len(digits) >= 2:
            out.append(f"{digits[0]}.{digits[1]}")
    return out
