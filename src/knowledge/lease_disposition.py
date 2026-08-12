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
# The folder holds something nobody has identified. That is NOT absence.
STATUS_UNIDENTIFIED = "unidentified_documents_in_folder"
# The instrument is missing but its terms are of record elsewhere. The row is
# FILLED and cited; what is owed is the document, not the facts.
STATUS_TERMS_SOURCED = "terms_sourced_instrument_missing"
# The instrument is here and cannot be read. Also not absence — and not a fetch.
STATUS_ILLEGIBLE = "instrument_illegible"

# `unplaced` means "I do not know what this is". Concluding "the instrument is
# not here" from it is inferring absence from ignorance: the file sitting in the
# folder may BE the lease. An unidentified document therefore produces a VERDICT
# item ("classify this file"), never a search item — a search sends the operator
# to a courthouse for a document that may already be on their disk.
UNPLACED = "unplaced"


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
    # What the FOLDER holds, kept separate from what the cells know. A lease can
    # have most of its terms of record and still have no instrument anywhere.
    folder_state: str = ""
    pointers: dict[str, Any] = field(default_factory=dict)

    def route(self) -> str:
        """Where the missing instrument is chased from.

        A lease whose FORM terms (royalty, term) are already of record teaches
        nobody anything at the courthouse — only the paper is owed, and the
        Seller owes paper. A lease with only its identity known still has facts
        to learn from the recording, so it is a lookup."""
        if self.status != STATUS_TERMS_SOURCED:
            return "fetch"
        form = {"royalty", "term"}
        return "seller" if form & set(self.proved_terms) else "fetch"

    def to_dict(self) -> dict[str, Any]:
        return {"lease": self.lease, "status": self.status,
                "folder_state": self.folder_state, "route": self.route(),
                "recording": self.recording, "sources": self.sources,
                "proved_terms": self.proved_terms,
                "unproved_terms": self.unproved_terms,
                "pointers": self.pointers,
                "defect": self.defect, "note": self.note}


def _rule(knowledge: Any) -> Any:
    return knowledge.taxonomy.categories["lease_memorandum"].dual_disposition


def dispose(lease: str, recording: str, classifications: list[dict[str, Any]],
            knowledge: Any, *, in_perimeter: bool = True,
            outside_reason: str = "",
            extra_sources: list[dict[str, Any]] | None = None) -> LeaseDisposition:
    """Decide a lease's disposition from what was READ — anywhere.

    `extra_sources` are documents that speak about OTHER entities: a title
    opinion whose schedule recites this lease, a ratification, an assignment.
    They are the reason a lease with no folder at all can still have most of its
    terms filled and cited."""
    if not in_perimeter:
        return LeaseDisposition(lease=lease, status=STATUS_OUTSIDE,
                                recording=recording, note=outside_reason)

    if not classifications and not extra_sources:
        return LeaseDisposition(
            lease=lease, status=STATUS_NOT_IN_CORPUS, recording=recording,
            note="no folder for this lease in the corpus")

    leases = [c for c in classifications if c.get("classified_as") == "lease_ogl"]
    memos = [c for c in classifications
             if c.get("classified_as") == "lease_memorandum"]

    if leases:
        # The instrument being present is not the end of the question. WHICH
        # terms it states is the rest of it, and skipping that is what made a
        # missing royalty on a present lease indistinguishable from a missing
        # lease — a row of blanks nobody owned.
        from src.knowledge.term_source import resolve

        d = LeaseDisposition(lease=lease, status=STATUS_OF_RECORD,
                             recording=recording,
                             sources=[_source(c) for c in leases])
        sourcing = resolve({"recording_book_page": recording,
                            "eog_lease_number": lease},
                           [*leases, *(extra_sources or [])], knowledge)
        d.proved_terms = {t: p.to_dict() for t, p in sourcing.proved.items()}
        d.unproved_terms = dict(sourcing.unproved)
        d.pointers = dict(sourcing.pointers)
        return d

    if memos:
        return _memo_only(lease, recording, memos, knowledge, extra_sources)

    illegible = [c for c in classifications if _is_illegible(c)]
    if illegible:
        return LeaseDisposition(
            lease=lease, status=STATUS_ILLEGIBLE, recording=recording,
            sources=[_source(c) for c in illegible],
            note=("the instrument is in the folder and could not be read. This "
                  "is a RE-SCAN or an open-it-by-hand, not a courthouse trip: "
                  "the document is already here."))

    unknown = [c for c in classifications if c.get("classified_as") == UNPLACED]
    if unknown:
        return LeaseDisposition(
            lease=lease, status=STATUS_UNIDENTIFIED, recording=recording,
            sources=[_source(c) for c in unknown],
            note=(f"{len(unknown)} document(s) in the folder were not identified. "
                  f"Absence of the instrument CANNOT be concluded while an "
                  f"unidentified file sits in the folder — one of them may be it."))

    # The instrument is not here. That does NOT mean its terms are unknown: an
    # of-record document elsewhere in the corpus may state them (rule
    # `proves_terms`). Sourcing fills CELLS; it does not make the document
    # present, and conflating the two made the fetch table vanish while every
    # instrument was still missing.
    sourced = _from_other_sources(lease, recording, extra_sources or [], knowledge)
    if sourced:
        sourced.sources.extend(_source(c) for c in classifications)
        sourced.status = (STATUS_TERMS_SOURCED if not classifications
                          else STATUS_TERMS_SOURCED)
        sourced.folder_state = (STATUS_NOT_IN_CORPUS if not classifications
                                else STATUS_NO_INSTRUMENT)
        return sourced

    # Only now is absence a claim the evidence supports: every document in the
    # folder was read AND identified, none is the instrument, and no other
    # of-record document states its terms. The negative knowledge IS the product
    # — "AUSTIN PRESBYTERIAN LSE 0220604-007.PDF" reads like the lease and is a
    # letter from EOG to the lessor, and only naming it keeps someone from
    # opening it again.
    return LeaseDisposition(
        lease=lease, status=STATUS_NO_INSTRUMENT, recording=recording,
        sources=[_source(c) for c in classifications],
        note=(f"{len(classifications)} documents read in the folder, all "
              f"identified; none is the lease instrument or a memorandum of it ("
              + ", ".join(f"{Path(str(c.get('file',''))).name} = "
                          f"{c.get('classified_as')}" for c in classifications[:6])
              + (", ..." if len(classifications) > 6 else "") + ")"))


def _from_other_sources(lease: str, recording: str,
                        extra_sources: list[dict[str, Any]],
                        knowledge: Any) -> LeaseDisposition | None:
    """Terms proved by a document that is about this lease without being it."""
    from src.knowledge.term_source import resolve

    if not extra_sources:
        return None
    key = {"recording_book_page": recording, "eog_lease_number": lease}
    sourcing = resolve(key, extra_sources, knowledge)
    if not sourcing.proved:
        return None

    d = LeaseDisposition(lease=lease, status=STATUS_TERMS_SOURCED,
                         recording=recording,
                         sources=list(sourcing.sources_used))
    d.proved_terms = {t: p.to_dict() for t, p in sourcing.proved.items()}
    d.unproved_terms = dict(sourcing.unproved)
    d.pointers = dict(sourcing.pointers)
    cite = next(iter(sourcing.proved.values())).citation()
    d.defect = {
        "label": "MISSING LEASE",
        "lease": lease,
        "destination": "potential_defects",
        "text": (f"{lease} — the recorded instrument is not in the file. Its "
                 f"terms are of record via {cite}; the instrument itself is "
                 f"requested from the Seller."),
        "owner": "Seller (EOG)",
        "evidence": cite,
    }
    d.note = (f"{len(sourcing.proved)} term(s) proved by {cite}; the instrument "
              f"is a delivery the Seller owes, not a document to go and learn "
              f"facts from")
    return d


# An illegible instrument announces itself: the reader says so, or the read
# produced nothing at all from a document that is plainly there.
_ILLEGIBLE_MARKS = ("illegible", "ilegivel", "unreadable", "cannot be read",
                    "too dark", "blank scan", "no text")


def _is_illegible(c: dict[str, Any]) -> bool:
    blob = " ".join(str(n) for n in (c.get("notes") or [])).lower()
    if any(mark in blob for mark in _ILLEGIBLE_MARKS):
        return True
    quote = str((c.get("evidence") or {}).get("quote") or "").lower()
    return any(mark in quote for mark in _ILLEGIBLE_MARKS)


def _memo_only(lease: str, recording: str, memos: list[dict[str, Any]],
               knowledge: Any, extra_sources: list[dict[str, Any]] | None = None
               ) -> LeaseDisposition:
    """The memorandum case, resolved through the SAME machinery as every other
    source. It had its own copy of the logic, which is how the pointer rule and
    the frame rule reached every category except the one they were written for."""
    from src.knowledge.term_source import resolve

    rule = _rule(knowledge)
    d = LeaseDisposition(lease=lease, status=STATUS_MEMO_ONLY,
                         recording=recording, sources=[_source(m) for m in memos])

    sourcing = resolve({"recording_book_page": recording,
                        "eog_lease_number": lease},
                       [*memos, *(extra_sources or [])], knowledge)
    d.proved_terms = {t: p.to_dict() for t, p in sourcing.proved.items()}
    d.unproved_terms = dict(sourcing.unproved)
    d.pointers = dict(sourcing.pointers)
    for term in MEMO_UNPROVABLE_TERMS:
        d.unproved_terms.setdefault(
            term, getattr(rule, "reason_for_unstated_terms", "doc_nao_localizado"))

    best = next((m for m in memos
                 if str((m.get("of_record") or {}).get("status")) == "recorded"),
                memos[0])
    page = (best.get("evidence") or {}).get("page", 1)
    cite = f"{Path(str(best.get('file', ''))).name} p.{page}"
    if sourcing.proved:
        cite = next(iter(sourcing.proved.values())).citation()

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
