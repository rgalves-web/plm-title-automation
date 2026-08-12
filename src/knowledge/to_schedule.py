"""A title opinion's LEASE SUMMARY, turned into `proves` entries.

The opinion recites each lease it examined — date, recording, lessor, royalty,
primary term. That recital is what lets a lease whose instrument is missing be a
FILLED row with a citation instead of a blank one, and it is why the missing
instrument becomes a delivery the Seller owes rather than a trip to learn facts
already in hand.

The entries key on RECORDING, never on the lessor's name (term_source enforces
it): the same lessor holds leases in several units, and the recording is the only
thing that tells them apart.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_FIELDS = ("DATE", "RECORDING", "LESSOR", "LESSEE", "LAND", "INTEREST_COVERED",
           "ROYALTY", "PRIMARY_TERM")
_TERM_OF = {"DATE": "instrument_date", "RECORDING": "recording",
            "LESSOR": "lessor", "LESSEE": "lessee", "LAND": "legal_description",
            "INTEREST_COVERED": "interest_covered", "ROYALTY": "royalty",
            "PRIMARY_TERM": "term"}
_UNKNOWN = {"", "?", "NONE", "N/A", "-"}


def parse_schedule(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """`blocks` are {page, text} from reading the LEASE SUMMARY pages."""
    entries: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    last: str | None = None
    for block in blocks:
        page = block.get("page")
        for line in str(block.get("text") or "").splitlines():
            head = re.match(r"^\s*LEASE\s+(\d{1,2})\s*$", line.strip(), re.I)
            if head:
                if current:
                    entries.append(current)
                current = {"lease_no": head.group(1), "page": page, "raw": {}}
                last = None
                continue
            if current is None:
                continue
            m = re.match(rf"^({'|'.join(_FIELDS)}):\s*(.*)$", line.strip())
            if m:
                current["raw"][m.group(1)] = m.group(2).strip()
                last = m.group(1)
            elif line.strip() and last:
                current["raw"][last] += " " + line.strip()
    if current:
        entries.append(current)

    out: list[dict[str, Any]] = []
    for e in entries:
        raw = e["raw"]
        terms = {_TERM_OF[k]: v for k, v in raw.items()
                 if k in _TERM_OF and str(v).strip().upper() not in _UNKNOWN}
        recording = raw.get("RECORDING", "")
        out.append({
            "lease_no": e["lease_no"], "page": e["page"],
            "recording_book_page": recording,
            "terms": terms,
            "quote": f"LEASE {e['lease_no']}: "
                     + "; ".join(f"{k}: {v}" for k, v in raw.items() if v)[:200],
        })
    return out


# "Leases 26 - 32 use the same form as Lease 10, and only those provisions
# differing from Lease 10 are included below." That is not an inference invited
# by a silent field — it is the opinion stating, in words, that the unstated
# provisions ARE the base lease's. Reading it any other way leaves thirteen
# royalty cells blank that the document actually fills.
_FORM_REF_RE = re.compile(
    r"Leases?\s+(\d{1,2})\s*(?:-|–|through|to)?\s*(\d{1,2})?\s+uses?\s+the\s+"
    r"same\s+form\s+as\s+Lease\s+(\d{1,2})", re.IGNORECASE)

# What a FORM carries. Identity never inherits: every entry prints its own
# recording, date and lessor, and inheriting those would merge two leases.
FORM_TERMS = ("royalty", "term", "shut_in", "pooling_clause", "depth_limitation")


def form_references(pages: list[str]) -> dict[str, tuple[str, int, str]]:
    """lease no -> (base lease no, page of the statement, the statement)."""
    out: dict[str, tuple[str, int, str]] = {}
    for page_no, text in enumerate(pages, start=1):
        for m in _FORM_REF_RE.finditer(text or ""):
            first, last, base = m.group(1), m.group(2), m.group(3)
            quote = " ".join(m.group(0).split())
            start, end = int(first), int(last or first)
            for n in range(start, end + 1):
                if str(n) != base:
                    out[str(n)] = (base, page_no, quote)
    return out


def apply_form_references(schedule: list[dict[str, Any]],
                          pages: list[str]) -> list[dict[str, Any]]:
    """Fill each entry's unstated FORM terms from the lease it points at.

    The chain is followed (26 -> 10 -> 9) and the citation keeps both pages, so
    the reader can see the borrowed value AND the sentence that authorises it."""
    refs = form_references(pages)
    by_no = {e["lease_no"]: e for e in schedule}

    def resolve(no: str, seen: frozenset[str]) -> None:
        if no in seen or no not in refs:
            return
        base_no, page_no, quote = refs[no]
        base = by_no.get(base_no)
        entry = by_no.get(no)
        if base is None or entry is None:
            return
        resolve(base_no, seen | {no})            # chains: 26 -> 10 -> 9
        for term in FORM_TERMS:
            if entry["terms"].get(term) or not base["terms"].get(term):
                continue
            entry["terms"][term] = base["terms"][term]
            entry.setdefault("inherited", {})[term] = {
                "from_lease": base_no, "from_page": base["page"],
                "authority_page": page_no, "quote": quote}

    for no in list(by_no):
        resolve(no, frozenset())
    return schedule


def as_document(opinion_path: str | Path, blocks: list[dict[str, Any]],
                cert_date: str = "",
                ocr_pages: list[str] | None = None) -> dict[str, Any]:
    """The opinion as a classification record carrying its `proves` entries."""
    schedule = parse_schedule(blocks)
    if ocr_pages:
        schedule = apply_form_references(schedule, ocr_pages)
    return {
        "file": str(opinion_path),
        "classified_as": "title_opinion",
        # An opinion filed of record is not the point here: what matters for
        # sourcing is that the recital is the examiner's signed statement about
        # instruments that ARE of record. The recording it recites is the
        # of-record fact; that is what `proves` carries.
        "of_record": {"status": "recorded",
                      "reason": "recites instruments by their recording"},
        "extracted": {"cert_date": cert_date},
        "proves": schedule,
    }


def unrecorded_in_schedule(schedule: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Leases the opinion itself says are NOT of record — a finding, not a gap
    in our corpus. Nobody can fetch a recording that does not exist."""
    return [e for e in schedule
            if re.search(r"unrecorded", str(e.get("recording_book_page") or ""),
                         re.IGNORECASE)]
