"""What each lease in the unit actually has, and what that means for the DDR.

The PLM supervisor's rule, in his words: *"note all this in your ddr, add the
leases that are memos as missing leases and get a new unit."* It is one rule
with two halves that must both hold at once, and it lives as data in
`knowledge/taxonomy/categories.yaml` under `lease_memorandum.dual_disposition`:

  - the recorded memorandum IS the of-record source for the terms it states —
    those cells are filled and cited to its page;
  - the lease is ALSO a MISSING LEASE under Potential Defects, with the complete
    instrument requested from the Seller;
  - and every term the memorandum does not state stays blank with a named reason
    from the closed vocabulary — never inferred from the memorandum's silence.

That last clause is the whole point. A memo-only lease used to produce either a
confident wrong answer (terms invented from the memo's silence) or a blank cell
nobody owned. It now produces exactly what is provable, cited, plus a named hole
with an owner.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# What a memorandum of lease typically does state, and therefore may prove.
MEMO_PROVABLE_TERMS = ("lessor", "lessee", "instrument_date", "recording",
                       "legal_description", "term")
# What it almost never states. Named here so the blank carries a reason instead
# of a shrug.
MEMO_UNPROVABLE_TERMS = ("royalty", "bonus", "pooling_clause", "shut_in",
                         "depth_limitation")

STATUS_OF_RECORD = "instrument_of_record"
STATUS_MEMO_ONLY = "memo_only"
STATUS_NO_INSTRUMENT = "no_instrument_in_folder"
STATUS_NOT_IN_CORPUS = "not_in_corpus"
STATUS_OUTSIDE = "outside_perimeter"


@dataclass
class LeaseDisposition:
    lease: str
    status: str
    recording: str = ""
    sources: list[dict[str, Any]] = field(default_factory=list)
    proved_terms: dict[str, dict[str, Any]] = field(default_factory=dict)
    unproved_terms: dict[str, str] = field(default_factory=dict)
    defect: dict[str, Any] | None = None
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"lease": self.lease, "status": self.status,
                "recording": self.recording, "sources": self.sources,
                "proved_terms": self.proved_terms,
                "unproved_terms": self.unproved_terms,
                "defect": self.defect, "note": self.note}


def _rule(knowledge: Any) -> Any:
    return knowledge.taxonomy.categories["lease_memorandum"].dual_disposition


def dispose(lease: str, recording: str, classifications: list[dict[str, Any]],
            knowledge: Any, *, in_perimeter: bool = True,
            outside_reason: str = "") -> LeaseDisposition:
    """Decide a lease's disposition from what was READ in its folder."""
    if not in_perimeter:
        return LeaseDisposition(lease=lease, status=STATUS_OUTSIDE,
                                recording=recording, note=outside_reason)

    if not classifications:
        return LeaseDisposition(
            lease=lease, status=STATUS_NOT_IN_CORPUS, recording=recording,
            note="no folder for this lease in the corpus")

    leases = [c for c in classifications if c.get("classified_as") == "lease_ogl"]
    memos = [c for c in classifications
             if c.get("classified_as") == "lease_memorandum"]

    if leases:
        return LeaseDisposition(
            lease=lease, status=STATUS_OF_RECORD, recording=recording,
            sources=[_source(c) for c in leases])

    if memos:
        return _memo_only(lease, recording, memos, knowledge)

    # The negative knowledge IS the product here: naming what the folder holds
    # is what stops the next round re-reading it. "AUSTIN PRESBYTERIAN LSE
    # 0220604-007.PDF" reads like the lease and is a letter from EOG to the
    # lessor; only saying so, by name, keeps someone from opening it again.
    return LeaseDisposition(
        lease=lease, status=STATUS_NO_INSTRUMENT, recording=recording,
        sources=[_source(c) for c in classifications],
        note=(f"{len(classifications)} documents read in the folder; none is the "
              f"lease instrument or a memorandum of it ("
              + ", ".join(f"{Path(str(c.get('file',''))).name} = "
                          f"{c.get('classified_as')}" for c in classifications[:6])
              + (", ..." if len(classifications) > 6 else "") + ")"))


def _memo_only(lease: str, recording: str, memos: list[dict[str, Any]],
               knowledge: Any) -> LeaseDisposition:
    rule = _rule(knowledge)
    # Prefer a recorded memorandum: only an of-record instrument may prove terms.
    recorded = [m for m in memos
                if str((m.get("of_record") or {}).get("status")) == "recorded"]
    best = (recorded or memos)[0]
    d = LeaseDisposition(lease=lease, status=STATUS_MEMO_ONLY,
                         recording=recording, sources=[_source(m) for m in memos])

    extracted = best.get("extracted") or {}
    page = (best.get("evidence") or {}).get("page", 1)
    cite = f"{Path(str(best.get('file', ''))).name} p.{page}"
    for term in MEMO_PROVABLE_TERMS:
        value = extracted.get(term)
        if value:
            d.proved_terms[term] = {"value": value, "cited_to": cite,
                                    "of_record": (best.get("of_record") or {})
                                    .get("status", "unknown")}
    for term in MEMO_UNPROVABLE_TERMS:
        if not extracted.get(term):
            d.unproved_terms[term] = getattr(rule, "reason_for_unstated_terms",
                                             "doc_nao_localizado")

    d.defect = {
        "label": getattr(rule, "defect_label", "MISSING LEASE"),
        "lease": lease,
        "destination": "potential_defects",
        "text": (f"{lease} — only the recorded memorandum is of record "
                 f"({recording or 'recording per Exhibit \"A\"'}); the complete "
                 f"lease instrument is requested from the Seller."),
        "owner": "Seller (EOG)",
        "evidence": cite,
    }
    d.note = (getattr(rule, "as_source", "") or "").strip()
    return d


def _source(c: dict[str, Any]) -> dict[str, Any]:
    return {"file": str(c.get("file", "")),
            "classified_as": c.get("classified_as"),
            "confidence": c.get("confidence"),
            "of_record": (c.get("of_record") or {}).get("status", "unknown"),
            "page": (c.get("evidence") or {}).get("page"),
            "quote": (c.get("evidence") or {}).get("quote", "")[:160]}


def summarise(dispositions: list[LeaseDisposition]) -> dict[str, int]:
    out: dict[str, int] = {}
    for d in dispositions:
        out[d.status] = out.get(d.status, 0) + 1
    return out
