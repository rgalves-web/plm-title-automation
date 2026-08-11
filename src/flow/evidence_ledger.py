"""Append-only evidence ledger — every file that enters a unit case.

The ledger is the single source of truth for *what documents this unit has and
what they are*. Its most important product is the **derived allowlist**: the set
of title-opinion / contract / lease identifiers the unit legitimately owns,
computed from confirmed evidence at run time. This permanently kills assessment
trap §3.1 — allowlists are never hand-typed, so a stale manifest can no longer
produce false ``foreign_unit_leakage``.

Nothing is discarded silently: a file the classifier could not place is recorded
with ``status=unplaced`` and a reason, so it is visible, not lost.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

# What a piece of evidence IS (drives allowlist buckets and the DROP screen).
KIND_TITLE_OPINION = "title_opinion"
KIND_CONTRACT = "contract"
KIND_LEASE = "lease"
KIND_DPU = "dpu"
KIND_WELL = "well"
KIND_RUNSHEET_INSTRUMENT = "runsheet_instrument"
KIND_REFERENCE = "reference"
KIND_UNKNOWN = "unknown"

# Lifecycle of one entry. A human confirm/correct makes it trustworthy; unplaced
# keeps an unrecognised file visible with a reason.
STATUS_DROPPED = "dropped"
STATUS_CLASSIFIED = "classified"
STATUS_CONFIRMED = "confirmed"
STATUS_CORRECTED = "corrected"
STATUS_UNPLACED = "unplaced"

# Statuses whose identifier may be trusted for allowlist derivation.
_TRUSTED = frozenset({STATUS_CONFIRMED, STATUS_CORRECTED})


@dataclass
class EvidenceEntry:
    file: str                        # source filename or archive-member path
    kind: str = KIND_UNKNOWN
    identifier: str | None = None    # T0140319 / K1400170 / 0190122-007 / ...
    status: str = STATUS_DROPPED
    confidence: float | None = None
    evidence_quote: str = ""         # the text/OCR snippet that justified the label
    page: str = ""
    cited_by: list[str] = field(default_factory=list)   # DDR cells, e.g. "Ownership Report!S14"
    reason: str = ""                 # why unplaced, or why blank/waived
    # OKF L0: the identity fields established for this entry, and what is still
    # missing. A reference that cannot fill its whole key is a CANDIDATE with
    # the gap named — it never promotes to confirmed on a partial key.
    identity: dict[str, Any] = field(default_factory=dict)
    missing_identity_fields: list[str] = field(default_factory=list)

    def is_trusted(self) -> bool:
        return self.status in _TRUSTED

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file, "kind": self.kind, "identifier": self.identifier,
            "status": self.status, "confidence": self.confidence,
            "evidence_quote": self.evidence_quote, "page": self.page,
            "cited_by": list(self.cited_by), "reason": self.reason,
            "identity": dict(self.identity),
            "missing_identity_fields": list(self.missing_identity_fields),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "EvidenceEntry":
        return cls(
            file=d["file"], kind=d.get("kind", KIND_UNKNOWN),
            identifier=d.get("identifier"), status=d.get("status", STATUS_DROPPED),
            confidence=d.get("confidence"), evidence_quote=d.get("evidence_quote", ""),
            page=d.get("page", ""), cited_by=list(d.get("cited_by", [])),
            reason=d.get("reason", ""), identity=dict(d.get("identity", {})),
            missing_identity_fields=list(d.get("missing_identity_fields", [])),
        )


@dataclass
class EvidenceLedger:
    entries: list[EvidenceEntry] = field(default_factory=list)

    # --- mutation (append-only in spirit; corrections add a corrected entry) ---
    def add(self, entry: EvidenceEntry) -> EvidenceEntry:
        self.entries.append(entry)
        return entry

    def record(self, file: str, kind: str, identifier: str | None = None,
               status: str = STATUS_CONFIRMED, **kw: Any) -> EvidenceEntry:
        return self.add(EvidenceEntry(file=file, kind=kind, identifier=identifier,
                                      status=status, **kw))

    # --- OKF L0/L2 conformance -------------------------------------------
    ENTITY_BY_KIND = {
        KIND_TITLE_OPINION: "title_opinion", KIND_CONTRACT: "instrument",
        KIND_LEASE: "lease", KIND_DPU: "instrument", KIND_WELL: "well",
        KIND_RUNSHEET_INSTRUMENT: "instrument",
    }

    def record_with_identity(self, file: str, kind: str, entity: str,
                             identity: dict[str, Any], knowledge: Any,
                             **kw: Any) -> EvidenceEntry:
        """Record an entry whose status follows its IDENTITY KEY.

        A complete key may be confirmed; an incomplete one is a candidate that
        names what it lacks. Nothing is promoted on a partial key (OKF L0)."""
        missing = knowledge.missing_identity_fields(entity, identity)
        status = STATUS_CLASSIFIED if missing else kw.pop("status", STATUS_CONFIRMED)
        kw.pop("status", None)
        return self.add(EvidenceEntry(
            file=file, kind=kind, identifier=kw.pop("identifier", None),
            status=status, identity=dict(identity),
            missing_identity_fields=missing, **kw))

    def conformance_problems(self, knowledge: Any) -> list[str]:
        """Every entry whose reason is outside the closed vocabulary, or that is
        confirmed on an incomplete identity key. Empty means the ledger obeys
        the knowledge base."""
        problems: list[str] = []
        for e in self.entries:
            if e.reason and not knowledge.is_valid_reason(e.reason):
                problems.append(
                    f"{e.file}: reason {e.reason!r} is not in the closed vocabulary")
            if e.is_trusted() and e.missing_identity_fields:
                problems.append(
                    f"{e.file}: confirmed while missing identity fields "
                    f"{e.missing_identity_fields}")
        return problems

    # --- queries ---
    def by_kind(self, kind: str) -> list[EvidenceEntry]:
        return [e for e in self.entries if e.kind == kind]

    def confirmed(self) -> list[EvidenceEntry]:
        return [e for e in self.entries if e.is_trusted()]

    def unplaced(self) -> list[EvidenceEntry]:
        return [e for e in self.entries if e.status == STATUS_UNPLACED]

    def identifiers(self, kind: str, trusted_only: bool = True) -> set[str]:
        return {
            e.identifier for e in self.entries
            if e.kind == kind and e.identifier
            and (e.is_trusted() or not trusted_only)
        }

    # --- the point of the whole module ---
    def derive_allowlist(self, unit_name: str) -> dict[str, Any]:
        """Compute what legitimately belongs to this unit from confirmed evidence.

        Returns a plain dict (the caller builds the engine's UnitAllowlist), so
        this module stays decoupled from ``src.dd``. Only CONFIRMED / CORRECTED
        evidence contributes — a merely-dropped or unplaced file never widens the
        allowlist."""
        from src.dd.agreements_xref import unit_identity_tokens

        return {
            "unit_name": unit_name,
            "title_opinions": self.identifiers(KIND_TITLE_OPINION),
            "contracts": self.identifiers(KIND_CONTRACT),
            "leases": self.identifiers(KIND_LEASE),
            "identity_tokens": set(unit_identity_tokens(unit_name)),
        }

    # --- persistence ---
    def to_dict(self) -> dict[str, Any]:
        return {"entries": [e.to_dict() for e in self.entries]}

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> "EvidenceLedger":
        d = d or {}
        return cls(entries=[EvidenceEntry.from_dict(e) for e in d.get("entries", [])])

    @classmethod
    def from_entries(cls, entries: Iterable[EvidenceEntry]) -> "EvidenceLedger":
        return cls(entries=list(entries))
