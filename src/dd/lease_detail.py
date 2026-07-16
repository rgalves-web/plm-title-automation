"""Per-lease ownership detail from the controlling title opinions (Collin items 1-2).

For each unit lease, match its lessor to a mineral owner in the controlling
tract's MINERALS section to get the Mineral Interest (MI) fraction, set EOG's
per-lease Working Interest (WI), and carry royalty over from the Lease Review
extraction. Purely deterministic: names matched by canonical key + fuzzy score,
all fractions in fractions.Fraction, every value carrying its TO source. The
totals-closing / MI-sum-to-1 checks live in dd_qa_gates, not here — this module
only assembles the values, it does not fudge them to fit.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any

from src.dd.name_match import match_person
from src.dd.unit_aggregation import (
    parse_fraction_text,
    reconcile_mineral_fraction,
    royalty_from_leasehold_formula,
)

_LEADING_FRACTION_RE = re.compile(r"(\d+\s*/\s*\d+|\d+(?:\.\d+)?\s*%|\d*\.\d+)")


def _leading_fraction(text: str | None) -> Fraction | None:
    """Parse the first fraction/percent/decimal in prose like
    '1/2 mineral interest' or '62.5% working interest'."""
    if not text:
        return None
    m = _LEADING_FRACTION_RE.search(str(text))
    return parse_fraction_text(m.group(1)) if m else None

# A lease's Working Interest is the SELLER's stated working interest for the
# tract that lease sits in, read from the controlling (most recent) opinion —
# never a default. There used to be a `_DEFAULT_LEASE_WI = Fraction(1)` here, on
# the theory that EOG holds the full leasehold and MI does the allocation. The
# opinions contradict it: Brumbaugh SUPP states EOG's WI as "(62.5% x 75%)
# .62500000" and Cox SUPP as ".84953704". Defaulting to 1 silently overstated
# every lease in those tracts. Where the controlling opinion states no WI for a
# tract, the value stays EMPTY with a reason — never guessed back to 1.


@dataclass
class LeaseDetail:
    lease_no: str
    lessor: str | None = None
    mi_value: Fraction | None = None
    wi_value: Fraction | None = None
    # How mi_value was resolved: "mineral_owner" = the lessor was name-matched to
    # a MINERALS-section owner (AUTHORITATIVE — this per-owner fraction always
    # wins); "lease_block" = fallback to the lease-analysis interest_covered when
    # no owner match existed (fill-only, never overwrites an owner-matched value).
    mi_source: str | None = None
    # Why MI is empty, when it is (pending-reasons layer, Maxwell lessons item 1):
    # one of the reason slugs in dd_pending.PendingReason. Recorded in the audit
    # layer — never written into a client-facing cell.
    mi_reason: str | None = None
    wi_reason: str | None = None       # why WI is empty, when it is
    wi_source: str | None = None       # the opinion + table the WI came from
    royalty: str | None = None
    royalty_source: str | None = None   # e.g. "leasehold_royalty_formula"
    tract_gross_acres: Fraction | None = None
    legal_description: str | None = None
    tract_key: str | None = None       # stable per-tract id for the ≤1/1 MI-sum gate
    source: str | None = None          # TO filename (+ section) the values came from
    notes: list[str] = field(default_factory=list)


def _iter_tract_owners(controlling: dict[str, Any]):
    """Yield (file_number, tract_index, tract, owner) across controlling tracts."""
    for file_number, extraction in controlling.items():
        for i, tract in enumerate(getattr(extraction, "tracts", []) or []):
            for owner in getattr(tract, "mineral_owners", []) or []:
                yield file_number, i, tract, owner


def _tract_gross(tract: Any, tract_gross_fn) -> Fraction | None:
    return tract_gross_fn(tract) if tract_gross_fn else None


def _apply_tract_wi(detail: LeaseDetail, tract: Any, file_number: str, tract_wi_fn) -> None:
    """Set the lease's WI from the controlling opinion's stated tract WI.

    Never falls back to a default: an unstated WI is left EMPTY with a reason, so
    a missing figure reads as missing instead of as "EOG owns all of it".
    """
    wi = tract_wi_fn(tract) if tract_wi_fn else None
    if wi is not None:
        detail.wi_value = wi
        detail.wi_source = f"{file_number} · leasehold estate table (Seller WI {wi})"
        return
    detail.wi_reason = "unresolved_fraction"
    detail.notes.append(
        f"{file_number} states no Seller working interest for this tract — WI left "
        "empty; read the opinion's LEASEHOLD ESTATE table.")


def _tract_key(file_number: str, tract: Any) -> str:
    """Stable per-tract identifier so the ≤1/1 MI-sum gate can group the leases
    that draw their mineral interest from the same tract."""
    legal = getattr(tract, "tract_legal_description", None)
    legal_val = getattr(legal, "value", None) if legal else None
    return f"{file_number}::{(legal_val or '?')[:60]}"


def build_lease_details(
    leases: list[Any],
    controlling: dict[str, Any],
    royalty_by_lease: dict[str, str] | None = None,
    tract_gross_fn=None,
    tract_wi_fn=None,
) -> list[LeaseDetail]:
    """Assemble a LeaseDetail per unit lease.

    leases: manifest.leases (each with .lease_no and .lessor).
    controlling: file_number -> TitleOpinionExtraction (the controlling opinions).
    royalty_by_lease: lease_no -> royalty text already resolved (e.g. from the
        Lease Review extraction) to carry into the Ownership Report.
    tract_gross_fn: callable(tract) -> Fraction | None for tract gross acres.
    tract_wi_fn: callable(tract) -> Fraction | None for the SELLER's stated
        working interest in that tract, per the controlling opinion. Because
        `controlling` already holds the newest opinion per chain, this reads the
        supplement's figure whenever one exists and the original is superseded.
    """
    royalty_by_lease = royalty_by_lease or {}
    owners = list(_iter_tract_owners(controlling))
    lease_blocks = list(_iter_lease_blocks(controlling))

    details: list[LeaseDetail] = []
    for lease in leases:
        lease_no = str(getattr(lease, "lease_no", "") or "")
        lessor = getattr(lease, "lessor", None)
        detail = LeaseDetail(lease_no=lease_no, lessor=lessor)

        # Carry royalty over first (Lease Review value wins; item 2 quick-wins).
        if lease_no in royalty_by_lease and royalty_by_lease[lease_no]:
            detail.royalty = royalty_by_lease[lease_no]

        # Match lessor -> mineral owner for MI + the owning tract's acreage/legal.
        # Structural name matching (surname + a given name), never a fuzzy score:
        # an ambiguous match yields NO value and is itemized for review.
        best = None
        owner_match = match_person(lessor, [str(o.party) for (_fn, _ti, _t, o) in owners])
        if owner_match.matched:
            file_number, _ti, tract, owner = owners[owner_match.index]
            best = (file_number, tract, owner)
        elif owner_match.ambiguous:
            detail.mi_reason = "unresolved_identity"
            detail.notes.append(f"unresolved_identity — {owner_match.reason}")

        if best is not None:
            file_number, tract, owner = best
            # Resolve MI, cross-validating a formula-vs-decimal conflict against
            # this owner's leasehold-royalty formula (a probable source typo is
            # reported, never silently corrected).
            mi, typo_note = reconcile_mineral_fraction(
                owner.fraction_text, _owner_royalty_formula(tract, owner))
            if mi is not None:
                detail.mi_value = mi
                detail.mi_source = "mineral_owner"  # authoritative per-owner MI
                if typo_note:
                    detail.notes.append(typo_note)
            else:
                detail.mi_reason = "unresolved_fraction"
                detail.notes.append(
                    f"mineral fraction {owner.fraction_text!r} did not parse — MI left empty")
            _apply_tract_wi(detail, tract, file_number, tract_wi_fn)
            detail.tract_gross_acres = _tract_gross(tract, tract_gross_fn)
            legal = getattr(tract, "tract_legal_description", None)
            detail.legal_description = getattr(legal, "value", None) if legal else None
            detail.tract_key = _tract_key(file_number, tract)
            detail.source = f"{file_number} · MINERALS section (owner: {owner.party})"
            # Royalty: when the lease analysis carries no explicit royalty, this
            # owner's leasehold-royalty formula ends in the lease royalty
            # (… x 1/5 -> 1/5), which is an exact statement of it.
            if detail.royalty is None:
                own_royalty = royalty_from_leasehold_formula(_owner_royalty_formula(tract, owner))
                if own_royalty is not None:
                    detail.royalty = str(own_royalty)
                    detail.royalty_source = "leasehold_royalty_formula"
            if detail.royalty is None:
                detail.royalty = _tract_royalty_text(tract)
            # Lease-vs-unit definition for legal/acreage is an open item (Trevor).
            detail.notes.append(
                "Legal description and tract gross acres populated at LEASE level "
                "(full tract); lease-vs-unit definition awaits Trevor's guidance.")
        else:
            # Pooled lease: lessor is not itself a named mineral owner. Fall back
            # to the lease-analysis block — match by lessor and read the mineral
            # interest the lease covers.
            block_match = _match_lease_block(lessor, lease_blocks)
            if block_match is not None:
                file_number, tract, block = block_match
                mi = _leading_fraction(getattr(block.interest_covered, "value", None))
                if mi is not None:
                    detail.mi_value = mi
                    detail.mi_source = "lease_block"  # fallback only — never overwrites an owner match
                _apply_tract_wi(detail, tract, file_number, tract_wi_fn)
                if detail.tract_gross_acres is None:
                    detail.tract_gross_acres = _tract_gross(tract, tract_gross_fn)
                if not detail.legal_description:
                    legal = getattr(block.land_covered, "value", None)
                    detail.legal_description = legal
                detail.tract_key = _tract_key(file_number, tract)
                if detail.royalty is None:
                    detail.royalty = getattr(block.royalty, "value", None)
                detail.source = f"{file_number} · lease-analysis (lessor: {lessor})"
                if detail.mi_value is None:
                    detail.mi_reason = detail.mi_reason or "unresolved_fraction"
                    detail.notes.append(
                        f"matched lease block for {lessor!r} but its covered mineral interest "
                        "did not parse — MI left empty; read the lease-analysis entry.")
            else:
                # The lessor holds no attributed mineral interest in the
                # controlling opinions — a scope question for the reviewer, not a
                # value to guess (Maxwell lessons item 8).
                detail.mi_reason = detail.mi_reason or "awaiting_reviewer_decision"
                detail.notes.append(
                    f"lessor {lessor!r} not matched to a mineral owner or lease-analysis "
                    "entry in the controlling opinions — MI/WI left empty; consult the "
                    "opinion's MINERALS and lease-analysis sections.")
        details.append(detail)
    return details


def _iter_lease_blocks(controlling: dict[str, Any]):
    for file_number, extraction in controlling.items():
        for tract in getattr(extraction, "tracts", []) or []:
            for block in getattr(tract, "leases", []) or []:
                yield file_number, tract, block


def _match_lease_block(lessor: str | None, lease_blocks: list):
    """The lease-analysis block whose lessor is the same party, by the same
    structural rule as the MINERALS match (ambiguity -> no match)."""
    if not lessor:
        return None
    candidates = [str(getattr(block.lessor, "value", "") or "")
                  for _fn, _tract, block in lease_blocks]
    result = match_person(lessor, candidates)
    return lease_blocks[result.index] if result.matched else None


def _owner_royalty_formula(tract: Any, owner: Any) -> str | None:
    """This owner's LEASEHOLD ROYALTY formula, used to cross-validate a MINERALS
    formula that contradicts its own printed decimal. Matched by party name so we
    compare the same person's two statements of the same interest."""
    royalty_owners = list(getattr(tract, "royalty_owners", []) or [])
    if not royalty_owners:
        return None
    result = match_person(str(owner.party), [str(o.party) for o in royalty_owners])
    if not result.matched:
        return None
    return getattr(royalty_owners[result.index], "fraction_text", None)


def _tract_royalty_text(tract: Any) -> str | None:
    owners = getattr(tract, "royalty_owners", []) or []
    for owner in owners:
        if getattr(owner, "fraction_text", None):
            return owner.fraction_text
    return None
