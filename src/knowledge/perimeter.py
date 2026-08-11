"""S2 SCOPE — the unit's perimeter, and every index that disagrees with it.

The DPU's Exhibit "A" is the AUTHORITY on what is in the unit. The XREF, the
Lease & Mineral Schedule and the Well List are indexes: useful, and wrong often
enough that the difference is the product. A lease the DPU names and the XREF
omits is not noise — it is a lease nobody would have fetched.

The perimeter also carries the abstract set, which is the cheapest filter the
work has: a document naming another abstract is outside the unit, and saying so
before any deep OCR is where the cost of a round is decided.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

# A survey is abstract + block; the same abstract in another block is another
# place (OKF L0 identity_keys.survey).
_ABSTRACT_RE = re.compile(r"\bA-?(\d{2,4})\b", re.IGNORECASE)
_BLOCK_RE = re.compile(r"\bBl(?:oc)?k?s?\.?\s*([0-9]+(?:\s*(?:and|&|,)\s*[0-9]+)*)",
                       re.IGNORECASE)


def abstracts_in(text: str) -> set[str]:
    return {m.group(1) for m in _ABSTRACT_RE.finditer(str(text or ""))}


def blocks_in(text: str) -> set[str]:
    out: set[str] = set()
    for m in _BLOCK_RE.finditer(str(text or "")):
        out.update(re.findall(r"\d+", m.group(1)))
    return out


@dataclass(frozen=True)
class SurveyScope:
    abstract: str
    blocks: frozenset[str] = frozenset()

    def covers(self, text: str) -> bool:
        """Is this text inside this survey scope?

        An abstract match is necessary. When the scope names blocks, the text
        must name one of them — the same abstract in a different block is a
        different place and has cost this project a wrong fetch before."""
        if self.abstract not in abstracts_in(text):
            return False
        if not self.blocks:
            return True
        found = blocks_in(text)
        return not found or bool(found & set(self.blocks))

    def label(self) -> str:
        if self.blocks:
            return f"A-{self.abstract} Blocks {'/'.join(sorted(self.blocks))}"
        return f"A-{self.abstract}"


@dataclass
class Divergence:
    kind: str                  # missing_from_index | conflicting_recording | outside_perimeter
    subject: str               # the lease / tract / document at issue
    authority_says: str
    index_says: str
    index_name: str
    reason: str                # from the closed vocabulary
    action: str = "confirm"    # confirm | fetch | request
    proof: str = ""            # file + page

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "subject": self.subject,
                "authority_says": self.authority_says, "index_says": self.index_says,
                "index_name": self.index_name, "reason": self.reason,
                "action": self.action, "proof": self.proof}


@dataclass
class Perimeter:
    unit: str
    surveys: list[SurveyScope] = field(default_factory=list)
    tracts: dict[str, str] = field(default_factory=dict)      # tract no -> description
    leases: dict[str, str] = field(default_factory=dict)      # lease no -> recording
    wells: list[str] = field(default_factory=list)            # APIs
    divergences: list[Divergence] = field(default_factory=list)
    authority: str = ""                                       # the DPU, with page
    # A DPU names the SURVEY; only the controlling title opinion narrows it to
    # BLOCKS. Josh B sits in A-319 Blocks 5 and 6 — an A-319 Block 12 document is
    # somewhere else entirely, and the refinement has to carry the document that
    # made it or nobody can check it later.
    block_sources: dict[str, str] = field(default_factory=dict)

    # --- the cheap filter -------------------------------------------------
    def covers(self, text: str) -> bool:
        return any(s.covers(text) for s in self.surveys)

    def outside_reason(self, text: str) -> str | None:
        """Why a document is outside, or None when it is inside.

        Returns a reason from the closed vocabulary so the SKIP is countable."""
        if self.covers(text):
            return None
        if abstracts_in(text):
            return "fora_do_perimetro"
        return None          # names no abstract: cannot be excluded on this basis

    def abstract_labels(self) -> list[str]:
        return [s.label() for s in self.surveys]

    def to_dict(self) -> dict[str, Any]:
        return {
            "unit": self.unit, "authority": self.authority,
            "surveys": [{"abstract": s.abstract, "blocks": sorted(s.blocks),
                         "blocks_source": self.block_sources.get(s.abstract, "")}
                        for s in self.surveys],
            "tracts": dict(self.tracts), "leases": dict(self.leases),
            "wells": list(self.wells),
            "divergences": [d.to_dict() for d in self.divergences],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Perimeter":
        return cls(
            unit=d["unit"], authority=d.get("authority", ""),
            surveys=[SurveyScope(s["abstract"], frozenset(s.get("blocks") or []))
                     for s in d.get("surveys", [])],
            tracts=dict(d.get("tracts", {})), leases=dict(d.get("leases", {})),
            wells=list(d.get("wells", [])),
            block_sources={s["abstract"]: s.get("blocks_source", "")
                           for s in d.get("surveys", []) if s.get("blocks_source")},
            divergences=[Divergence(**x) for x in d.get("divergences", [])])


# ---------------------------------------------------------------------------
# Building it
# ---------------------------------------------------------------------------

def cross_check(perimeter: Perimeter, index_name: str,
                index_leases: dict[str, str]) -> list[Divergence]:
    """Diff an index against the authority and return what disagrees.

    Two shapes matter and they are NOT the same finding:
      - the authority names a lease the index omits — somebody has to fetch a
        document nobody knew to look for;
      - both name it, with different recordings — nothing is missing; a human
        has to decide which record is right.
    """
    found: list[Divergence] = []
    for lease, recording in perimeter.leases.items():
        if lease not in index_leases:
            found.append(Divergence(
                kind="missing_from_index", subject=lease,
                authority_says=f"in Exhibit A ({recording})" if recording else "in Exhibit A",
                index_says="absent", index_name=index_name,
                reason="doc_nao_localizado", action="fetch",
                proof=perimeter.authority))
        elif recording and index_leases[lease] and \
                _norm_recording(recording) != _norm_recording(index_leases[lease]):
            found.append(Divergence(
                kind="conflicting_recording", subject=lease,
                authority_says=recording, index_says=index_leases[lease],
                index_name=index_name, reason="confirmar_no_cartorio",
                action="confirm", proof=perimeter.authority))
    return found


def _norm_recording(value: str) -> str:
    digits = re.findall(r"\d+", str(value or ""))
    return ".".join(digits[:2])


def build_perimeter(unit: str, authority: str, surveys: Iterable[SurveyScope],
                    exhibit_a_leases: dict[str, str],
                    tracts: dict[str, str] | None = None,
                    wells: Iterable[str] = (),
                    indexes: dict[str, dict[str, str]] | None = None) -> Perimeter:
    """Assemble the perimeter from the authority, then diff every index at it.

    `exhibit_a_leases` and `surveys` come from READING the DPU (its Exhibit "A"
    and the legal descriptions), with the page recorded in `authority`. This
    function does not guess them: it is given what was read, and it is
    responsible for what the reading implies."""
    p = Perimeter(unit=unit, authority=authority, surveys=list(surveys),
                  tracts=dict(tracts or {}), leases=dict(exhibit_a_leases),
                  wells=list(wells))
    for index_name, index_leases in (indexes or {}).items():
        p.divergences.extend(cross_check(p, index_name, index_leases))
    return p


def write_perimeter(perimeter: Perimeter, case_dir: str | Path) -> Path:
    import yaml

    from src.flow.deliverable_io import assert_not_frozen

    case_dir = Path(assert_not_frozen(case_dir))
    case_dir.mkdir(parents=True, exist_ok=True)
    path = case_dir / "perimeter.yaml"
    path.write_text(yaml.safe_dump(perimeter.to_dict(), sort_keys=False,
                                   allow_unicode=True), encoding="utf-8")
    return path
