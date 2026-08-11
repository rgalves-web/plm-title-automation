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


def as_document(opinion_path: str | Path, blocks: list[dict[str, Any]],
                cert_date: str = "") -> dict[str, Any]:
    """The opinion as a classification record carrying its `proves` entries."""
    schedule = parse_schedule(blocks)
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
