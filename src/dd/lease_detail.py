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

from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any

from rapidfuzz import fuzz

from src.dd.unit_aggregation import parse_fraction_text
from src.ownership import canonical_party_key

# EOG holds the full working interest under a standard leasehold; the mineral
# fraction (MI) does the allocation in the template's R×S×T net-acres formula.
# Where a lease is not a straight 100% WI leasehold, the seller-WI gate catches
# the resulting aggregate mismatch rather than this module guessing.
_DEFAULT_LEASE_WI = Fraction(1)
_MATCH_THRESHOLD = 82  # rapidfuzz token_sort_ratio on canonical party keys


@dataclass
class LeaseDetail:
    lease_no: str
    lessor: str | None = None
    mi_value: Fraction | None = None
    wi_value: Fraction | None = None
    royalty: str | None = None
    tract_gross_acres: Fraction | None = None
    legal_description: str | None = None
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


def build_lease_details(
    leases: list[Any],
    controlling: dict[str, Any],
    royalty_by_lease: dict[str, str] | None = None,
    tract_gross_fn=None,
) -> list[LeaseDetail]:
    """Assemble a LeaseDetail per unit lease.

    leases: manifest.leases (each with .lease_no and .lessor).
    controlling: file_number -> TitleOpinionExtraction (the controlling opinions).
    royalty_by_lease: lease_no -> royalty text already resolved (e.g. from the
        Lease Review extraction) to carry into the Ownership Report.
    tract_gross_fn: callable(tract) -> Fraction | None for tract gross acres.
    """
    royalty_by_lease = royalty_by_lease or {}
    owners = list(_iter_tract_owners(controlling))

    details: list[LeaseDetail] = []
    for lease in leases:
        lease_no = str(getattr(lease, "lease_no", "") or "")
        lessor = getattr(lease, "lessor", None)
        detail = LeaseDetail(lease_no=lease_no, lessor=lessor)

        # Carry royalty over first (Lease Review value wins; item 2 quick-wins).
        if lease_no in royalty_by_lease and royalty_by_lease[lease_no]:
            detail.royalty = royalty_by_lease[lease_no]

        # Match lessor -> mineral owner for MI + the owning tract's acreage/legal.
        best = None
        best_score = 0.0
        if lessor:
            lessor_key = canonical_party_key(lessor)
            for file_number, ti, tract, owner in owners:
                owner_key = canonical_party_key(str(owner.party))
                if not owner_key:
                    continue
                score = fuzz.token_sort_ratio(lessor_key, owner_key)
                if score > best_score and score >= _MATCH_THRESHOLD:
                    best_score, best = score, (file_number, tract, owner)

        if best is not None:
            file_number, tract, owner = best
            mi = parse_fraction_text(owner.fraction_text)
            if mi is not None:
                detail.mi_value = mi
                detail.wi_value = _DEFAULT_LEASE_WI
            else:
                detail.notes.append(
                    f"mineral fraction {owner.fraction_text!r} did not parse — MI left empty")
            detail.tract_gross_acres = _tract_gross(tract, tract_gross_fn)
            legal = getattr(tract, "tract_legal_description", None)
            detail.legal_description = getattr(legal, "value", None) if legal else None
            detail.source = f"{file_number} · MINERALS section (owner: {owner.party})"
            # Royalty fallback: the matched tract's royalty_owners / tract royalty.
            if detail.royalty is None:
                detail.royalty = _tract_royalty_text(tract)
            # Lease-vs-unit definition for legal/acreage is an open item (Trevor).
            detail.notes.append(
                "Legal description and tract gross acres populated at LEASE level "
                "(full tract); lease-vs-unit definition awaits Trevor's guidance.")
        else:
            detail.notes.append(
                f"lessor {lessor!r} not matched to a mineral owner in the controlling "
                "opinions — MI/WI left empty; consult the title opinion's MINERALS section.")
        details.append(detail)
    return details


def _tract_royalty_text(tract: Any) -> str | None:
    owners = getattr(tract, "royalty_owners", []) or []
    for owner in owners:
        if getattr(owner, "fraction_text", None):
            return owner.fraction_text
    return None
