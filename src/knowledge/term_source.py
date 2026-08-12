"""Which document proves which term — for any document type.

The rule used to be written on one category: "a recorded memorandum is the
of-record source for the terms it states". That was never a rule about
memoranda. What makes a document a source is being **of record** and **stating
the term**; the memorandum was simply the first case anyone hit.

Generalised, it changes what a missing document costs. A title opinion's LEASE
SUMMARY recites each lease it examined — date, recording, lessor, royalty,
primary term — so a lease whose instrument is not in the folder but whose terms
the opinion recites is not a blank row. It is a filled row with a citation, plus
one missing instrument. The instrument still has to arrive; it is a delivery the
Seller owes, not a courthouse trip to learn facts already in hand.

Two disciplines keep this from becoming wishful thinking:

  MATCH ON IDENTITY, NEVER ON A NAME. The link between an opinion's schedule and
  a lease is the RECORDING. The same lessor holds leases in several units, and
  a name match cheerfully imports another unit's terms. A lease the opinion does
  not schedule gets nothing from it — coverage is never assumed from the opinion
  merely being in the folder.

  SILENCE IS NOT A VALUE. A term the source does not state stays blank with a
  reason from the closed vocabulary. Nothing is inferred from what a document
  declined to say.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# When two of-record sources state the same term, this decides. The instrument
# outranks the short form of itself, which outranks an examiner's recital of it.
SOURCE_PRECEDENCE = ("lease_ogl", "lease_memorandum", "assignment",
                     "title_opinion", "ownership_report")


@dataclass
class ProvedTerm:
    term: str
    value: Any
    source_file: str
    source_page: Any
    source_category: str
    quote: str = ""
    # Set when the value came from a lease the source says shares this one's
    # form. The citation then carries BOTH pages: the borrowed value and the
    # sentence that authorises borrowing it.
    inherited_from: dict[str, Any] | None = None

    def citation(self) -> str:
        page = f" p.{self.source_page}" if self.source_page else ""
        base = f"{Path(str(self.source_file)).name}{page}"
        if self.inherited_from:
            base += (f" (form of Lease {self.inherited_from['from_lease']}, "
                     f"p.{self.inherited_from['from_page']}; authorised at "
                     f"p.{self.inherited_from['authority_page']}: "
                     f"\"{self.inherited_from['quote']}\")")
        return base

    def to_dict(self) -> dict[str, Any]:
        return {"term": self.term, "value": self.value,
                "cited_to": self.citation(),
                "source_category": self.source_category, "quote": self.quote,
                "inherited_from": self.inherited_from}


@dataclass
class TermSourcing:
    proved: dict[str, ProvedTerm] = field(default_factory=dict)
    unproved: dict[str, str] = field(default_factory=dict)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    sources_used: list[dict[str, Any]] = field(default_factory=list)
    # Values read faithfully but expressed in the source's own frame. Kept as
    # pointers; never adopted as a cell value.
    pointers: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"proved": {k: v.to_dict() for k, v in self.proved.items()},
                "unproved": dict(self.unproved),
                "conflicts": list(self.conflicts),
                "pointers": dict(self.pointers),
                "sources_used": list(self.sources_used)}


def norm_recording(value: Any) -> str:
    """Vol/Pg as a comparable key. Anything unrecorded compares to nothing."""
    digits = re.findall(r"\d+", str(value or ""))
    return ".".join(digits[:2]) if len(digits) >= 2 else ""


def _matches(rule: Any, key: dict[str, Any], entry: dict[str, Any]) -> bool:
    """The entry is about this entity iff one identity field agrees.

    `match_on` is the whitelist; a field outside it (a lessor name, say) can
    never make the match, however convincing it looks."""
    for field_name in rule.match_on:
        want, got = key.get(field_name), entry.get(field_name)
        if not want or not got:
            continue
        if field_name == "recording_book_page":
            if norm_recording(want) and norm_recording(want) == norm_recording(got):
                return True
        elif str(want).strip().lower() == str(got).strip().lower():
            return True
    return False


def resolve(key: dict[str, Any], documents: list[dict[str, Any]],
            knowledge: Any, wanted: list[str] | None = None) -> TermSourcing:
    """Which of `wanted` terms are proved for this entity, and by what.

    `documents` are classification records. A record may carry `proves`: a list
    of entries this document makes statements about, each with its identity
    fields, its `page`, and its `terms`. A document with no `proves` speaks only
    about itself, using its own `extracted` fields."""
    out = TermSourcing()
    candidates: list[tuple[int, str, dict[str, Any], dict[str, Any], Any]] = []

    for doc in documents:
        category = str(doc.get("classified_as") or "")
        try:
            rule = knowledge.taxonomy.categories[category].proves_terms
        except KeyError:
            rule = None
        if rule is None:
            continue
        if str((doc.get("of_record") or {}).get("status")) != "recorded":
            # Only an of-record document proves anything (flow spec §2 rule 5).
            continue
        rank = (SOURCE_PRECEDENCE.index(category)
                if category in SOURCE_PRECEDENCE else len(SOURCE_PRECEDENCE))
        for entry in _entries(doc):
            if _matches(rule, key, entry):
                candidates.append((rank, category, doc, entry, rule))

    candidates.sort(key=lambda c: c[0])
    for rank, category, doc, entry, rule in candidates:
        # Same key name the classification records use, so a consumer never has
        # to know whether a source spoke about itself or about someone else.
        out.sources_used.append({"file": str(doc.get("file", "")),
                                 "classified_as": category,
                                 "page": entry.get("page")})
        for term in getattr(rule, "frame_local", []) or []:
            value = (entry.get("terms") or {}).get(term)
            if value and term not in out.pointers:
                out.pointers[term] = {
                    "value": value, "source": str(doc.get("file", "")),
                    "page": entry.get("page"),
                    "why_not_adopted": (f"stated in the {category}'s own frame; "
                                        f"needs translation before it can be a "
                                        f"cell value")}

        for term in rule.proves:
            value = (entry.get("terms") or {}).get(term)
            if not value:
                continue
            if _is_pointer(value):
                # "SEE EXHIBIT 'A' ATTACHED HERETO FOR DESCRIPTION OF LANDS
                # COVERED" is a cross-reference, not a description. Transcribing
                # it faithfully still puts a signpost where a value belongs.
                out.pointers.setdefault(term, {
                    "value": value, "source": str(doc.get("file", "")),
                    "page": entry.get("page"),
                    "why_not_adopted": "the field cross-references another "
                                       "document instead of stating the value"})
                continue
            inherited = (entry.get("inherited") or {}).get(term)
            proved = ProvedTerm(term=term, value=value,
                                source_file=str(doc.get("file", "")),
                                source_page=entry.get("page"),
                                source_category=category,
                                quote=str(entry.get("quote") or "")[:200],
                                inherited_from=inherited)
            existing = out.proved.get(term)
            if existing is None:
                out.proved[term] = proved
            elif _differs(existing.value, value):
                # Two of-record sources disagreeing is a finding, not a merge.
                out.conflicts.append({
                    "term": term, "adopted": existing.to_dict(),
                    "conflicts_with": proved.to_dict(),
                    "why_adopted": f"{existing.source_category} outranks {category}"})

    for term in (wanted or _all_wanted(candidates)):
        if term in out.proved:
            continue
        reason = next((r.reason_for_unstated_terms for *_, r in candidates), None)
        out.unproved[term] = reason or "doc_nao_localizado"
    return out


def _entries(doc: dict[str, Any]) -> list[dict[str, Any]]:
    proves = doc.get("proves")
    if proves:
        return list(proves)
    extracted = dict(doc.get("extracted") or {})
    return [{"recording_book_page": extracted.get("recording"),
             "eog_lease_number": extracted.get("eog_lease_number"),
             "page": (doc.get("evidence") or {}).get("page"),
             "quote": (doc.get("evidence") or {}).get("quote", ""),
             "terms": extracted}]


def _all_wanted(candidates: list[tuple]) -> list[str]:
    wanted: list[str] = []
    for *_, rule in candidates:
        for term in list(rule.proves) + list(rule.cannot_prove):
            if term not in wanted:
                wanted.append(term)
    return wanted


def _differs(a: Any, b: Any) -> bool:
    """Loose equality — "Vol. 438, page 150" and "Volume 438, Pg. 150" agree."""
    na, nb = norm_recording(a), norm_recording(b)
    if na and nb:
        return na != nb
    clean = lambda v: re.sub(r"[^a-z0-9]", "", str(v).lower())  # noqa: E731
    return clean(a) != clean(b)


# A field that points somewhere else is not a value. These are the forms the
# corpus actually uses; each one was found sitting in a cell that needed a fact.
_POINTER_RE = re.compile(
    r"\bsee\s+(exhibit|attached|schedule|above|below)\b"
    r"|\battached\s+hereto\b"
    r"|\bas\s+(?:more\s+fully\s+)?described\s+in\b"
    r"|^\s*(?:same\s+as|per)\b", re.IGNORECASE)


def _is_pointer(value: Any) -> bool:
    return bool(_POINTER_RE.search(str(value or "")))
