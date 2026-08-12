"""Load and validate everything under `knowledge/`.

A schema error breaks the BOOT, not the run: knowledge that fails validation is
knowledge nobody can trust, and discovering that halfway through a unit is
worse than refusing to start. Parsed files are cached by content hash, so an
edit is picked up without a restart and an unchanged file is never re-parsed.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

KNOWLEDGE_DIRNAME = "knowledge"


class KnowledgeError(RuntimeError):
    """knowledge/ does not validate — the system must not boot on it."""


# --- L0 -------------------------------------------------------------------

class RelationDef(BaseModel):
    from_: str = Field(alias="from")
    to: str
    proof: str

    model_config = {"populate_by_name": True}


class EntityDef(BaseModel):
    label: str
    description: str
    relations: list[str] = Field(default_factory=list)


class Ontology(BaseModel):
    version: int
    entities: dict[str, EntityDef]
    relations: dict[str, RelationDef]

    @field_validator("entities")
    @classmethod
    def _entities_not_empty(cls, v: dict[str, EntityDef]) -> dict[str, EntityDef]:
        if not v:
            raise ValueError("ontology defines no entities")
        return v

    def check_relations_resolve(self) -> None:
        """Every relation names entities that exist, and every entity's
        declared relations exist. A dangling edge is a silent hole in the graph."""
        for name, rel in self.relations.items():
            for side in (rel.from_, rel.to):
                if side not in self.entities:
                    raise ValueError(
                        f"relation {name!r} names unknown entity {side!r}")
        for ent_name, ent in self.entities.items():
            for rel in ent.relations:
                if rel not in self.relations:
                    raise ValueError(
                        f"entity {ent_name!r} declares unknown relation {rel!r}")


class IdentityKey(BaseModel):
    required: list[str]
    never_identify_by: list[str] = Field(default_factory=list)
    alternates: list[str] = Field(default_factory=list)
    note: str | None = None

    @field_validator("required")
    @classmethod
    def _must_require_something(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("an identity key must require at least one field")
        return v


class IdentityKeys(BaseModel):
    version: int
    keys: dict[str, IdentityKey]
    reference_states: list[str]

    @field_validator("reference_states")
    @classmethod
    def _states(cls, v: list[str]) -> list[str]:
        if "candidate" not in v or "confirmed" not in v:
            raise ValueError("reference_states must include candidate and confirmed")
        return v


# --- L1 -------------------------------------------------------------------

RISK_TIERS = ("high", "low")


class ProvesTerms(BaseModel):
    """An of-record document that STATES a term is the source of that term.

    This is the general rule; the memorandum was only the first instance of it.
    A recorded memorandum, a title opinion whose lease summary recites a lease,
    a ratification — each is of record, each declares terms, and each therefore
    fills those cells with a citation to its own page. The document that is
    missing is still missing; the terms it would have proved are not.

    `for_entity` says whose terms this document proves (a title opinion proves
    the terms of the LEASES it schedules, not of itself). `match_on` is the
    identity that links the two — never a name, always the recording, because
    the same lessor holds leases in several units."""
    for_entity: str
    match_on: list[str]
    proves: list[str]
    cannot_prove: list[str] = Field(default_factory=list)
    # Terms whose value is only meaningful INSIDE the source document. A title
    # opinion's lease summary says `LAND: Tract 2` — its own tract numbering,
    # not the unit's. Transcribing it into the DDR's LEGAL DESCRIPTION column is
    # verbatim-correct and wrong where it lands. Such a term is recorded as a
    # POINTER and never adopted as the cell value: the cell stays blank with its
    # named reason until someone translates the frame.
    frame_local: list[str] = Field(default_factory=list)
    reason_for_unstated_terms: str
    # A source may also be a defect: a lease whose ONLY record is a memorandum
    # is reported missing at the same time as its terms are filled in.
    also_a_defect: bool = False
    defect_label: str | None = None
    note: str | None = None


class DualDisposition(BaseModel):
    """Retained name for the memorandum's shape; see ProvesTerms for the rule."""
    as_source: str
    as_defect: str
    terms_it_cannot_prove: str
    reason_for_unstated_terms: str
    defect_label: str


class Category(BaseModel):
    label: str
    feeds: list[str]
    identity_fields: list[str] = Field(default_factory=list)
    alternate_identity_fields: list[str] = Field(default_factory=list)
    relevance_test: str
    disposition_default: str
    risk_tier: str
    variants: list[str] = Field(default_factory=list)
    looks_like: str | None = None
    precedence: str | None = None
    authority: str | None = None
    note: str | None = None
    of_record: bool | None = None
    reason: str | None = None
    dual_disposition: DualDisposition | None = None
    proves_terms: ProvesTerms | None = None

    @field_validator("risk_tier")
    @classmethod
    def _tier(cls, v: str) -> str:
        if v not in RISK_TIERS:
            raise ValueError(f"risk_tier must be one of {RISK_TIERS}; got {v!r}")
        return v

    @field_validator("disposition_default")
    @classmethod
    def _disposition(cls, v: str) -> str:
        allowed = {"read", "skip", "hold"}
        if v not in allowed:
            raise ValueError(f"disposition_default must be in {sorted(allowed)}; got {v!r}")
        return v


class Taxonomy(BaseModel):
    version: int
    categories: dict[str, Category]
    feedless_allowed: list[str] = Field(default_factory=list)

    def check_every_category_feeds_something(self) -> None:
        """OKF invariant 2: a category that feeds nothing does not exist.

        The only exceptions are dispositions rather than destinations, and they
        must say so by name in feedless_allowed."""
        for name, cat in self.categories.items():
            if not cat.feeds and name not in self.feedless_allowed:
                raise ValueError(
                    f"category {name!r} feeds nothing — either give it a "
                    f"destination or declare it in feedless_allowed")

    def high_risk(self) -> set[str]:
        return {n for n, c in self.categories.items() if c.risk_tier == "high"}


class Destination(BaseModel):
    resolves_to: list[str] = Field(default_factory=list)
    section: str | None = None
    writes: list[str] = Field(default_factory=list)
    writes_to_case: str | None = None
    writes_to_package: str | None = None
    admits_only_of_record: bool = False


class CategoryToDDR(BaseModel):
    version: int
    destinations: dict[str, Destination]

    def resolve_tab(self, destination: str, template_tabs: list[str]) -> str | None:
        """The template's real tab for a logical destination, or None.

        Template versions differ across PLM ("Ownership Report" here,
        "Ownership - Worksheet" in the Knox example), so the mapping is resolved
        by introspecting the template delivered for THIS job. None means the
        writer cannot place the category — a blocking finding at OPEN."""
        dest = self.destinations.get(destination)
        if dest is None:
            return None
        for alias in dest.resolves_to:
            if alias in template_tabs:
                return alias
        return None


# --- L2 -------------------------------------------------------------------

class ExclusionReason(BaseModel):
    label: str
    applies_to: list[str]
    definition: str
    requires: list[str] = Field(default_factory=list)

    @field_validator("applies_to")
    @classmethod
    def _applies(cls, v: list[str]) -> list[str]:
        allowed = {"skip", "unplaced", "blank", "pending"}
        bad = set(v) - allowed
        if bad or not v:
            raise ValueError(f"applies_to must be a non-empty subset of {sorted(allowed)}; got {v}")
        return v


class ExclusionReasons(BaseModel):
    version: int
    reasons: dict[str, ExclusionReason]
    blank_reasons: list[str]

    @field_validator("reasons")
    @classmethod
    def _not_empty(cls, v: dict[str, ExclusionReason]) -> dict[str, ExclusionReason]:
        if not v:
            raise ValueError("the reason vocabulary is empty")
        return v

    def check_blank_reasons_exist(self) -> None:
        for name in self.blank_reasons:
            if name not in self.reasons:
                raise ValueError(f"blank_reasons names unknown reason {name!r}")
            if "blank" not in self.reasons[name].applies_to:
                raise ValueError(f"reason {name!r} is listed as a blank reason "
                                 "but does not apply to blanks")


# --- the bundle -----------------------------------------------------------

@dataclass(frozen=True)
class Knowledge:
    root: Path
    ontology: Ontology
    identity_keys: IdentityKeys
    exclusion_reasons: ExclusionReasons
    taxonomy: Taxonomy
    category_to_ddr: CategoryToDDR
    # Source recipes stay a plain mapping: they are read by the brief renderer
    # and the forbidden-method gate, and they grow a key per new source without
    # a schema change every time.
    sources: dict
    digest: str

    def category(self, name: str) -> Category:
        try:
            return self.taxonomy.categories[name]
        except KeyError:
            raise KnowledgeError(f"unknown category {name!r}")

    def needs_human_verdict(self, category: str, confidence: float | None = None,
                            floor: float = 0.0) -> bool:
        """D5: high-risk categories always; anything below the floor always."""
        if category not in self.taxonomy.categories:
            return True                                   # unknown -> human
        if confidence is not None and confidence < floor:
            return True
        return self.taxonomy.categories[category].risk_tier == "high"

    # Convenience the rest of the system asks for constantly.
    def identity_key(self, entity: str) -> IdentityKey:
        try:
            return self.identity_keys.keys[entity]
        except KeyError:
            raise KnowledgeError(f"no identity key defined for entity {entity!r}")

    def missing_identity_fields(self, entity: str, present: dict[str, Any]) -> list[str]:
        """Which required fields a reference still lacks. Empty means the key is
        complete and the reference may be `confirmed`; anything else keeps it a
        `candidate` with the gap named (invariant: never confirm on a partial key)."""
        key = self.identity_key(entity)
        return [f for f in key.required
                if present.get(f) in (None, "", [], {})]

    def is_valid_reason(self, reason: str, context: str | None = None) -> bool:
        r = self.exclusion_reasons.reasons.get(reason)
        if r is None:
            return False
        return context is None or context in r.applies_to

    def valid_reasons(self, context: str | None = None) -> set[str]:
        return {name for name, r in self.exclusion_reasons.reasons.items()
                if context is None or context in r.applies_to}


def _digest_dir(root: Path) -> str:
    """Content hash of every YAML under knowledge/, so the cache keys on what
    the files SAY, not on when they were touched."""
    h = hashlib.sha256()
    for path in sorted(root.rglob("*.yaml")):
        h.update(str(path.relative_to(root)).encode("utf-8"))
        h.update(path.read_bytes())
    return h.hexdigest()


def _read(root: Path, relative: str) -> dict[str, Any]:
    import yaml

    path = root / relative
    if not path.exists():
        raise KnowledgeError(f"knowledge/ is missing {relative}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise KnowledgeError(f"{relative} does not parse to a mapping")
    return data


def _parse(root: Path) -> Knowledge:
    try:
        ontology = Ontology(**_read(root, "ontology/entities.yaml"))
        ontology.check_relations_resolve()
        identity = IdentityKeys(**_read(root, "ontology/identity_keys.yaml"))
        reasons = ExclusionReasons(**_read(root, "rules/exclusion_reasons.yaml"))
        reasons.check_blank_reasons_exist()
        taxonomy = Taxonomy(**_read(root, "taxonomy/categories.yaml"))
        taxonomy.check_every_category_feeds_something()
        cat_to_ddr = CategoryToDDR(**_read(root, "taxonomy/category_to_ddr.yaml"))
        sources = _read(root, "rules/sources.yaml")
        for name, recipe in (sources.get("sources") or {}).items():
            if not recipe.get("action"):
                raise ValueError(f"source {name!r} declares no action (fetch/request)")
    except (ValidationError, ValueError) as exc:
        raise KnowledgeError(f"knowledge/ failed validation:\n{exc}") from exc
    # Every destination a category feeds must exist in the mapping, and every
    # reason a category names must be in the closed vocabulary.
    known_destinations = set(cat_to_ddr.destinations)
    for name, cat in taxonomy.categories.items():
        for dest in cat.feeds:
            if dest not in known_destinations:
                raise KnowledgeError(
                    f"category {name!r} feeds unknown destination {dest!r}")
        for reason in filter(None, [cat.reason,
                                    getattr(cat.dual_disposition, "reason_for_unstated_terms", None)]):
            if reason not in reasons.reasons:
                raise KnowledgeError(
                    f"category {name!r} names reason {reason!r}, which is not "
                    "in the closed vocabulary")
    # Every entity that has an identity key must exist in the ontology.
    unknown = set(identity.keys) - set(ontology.entities)
    if unknown:
        raise KnowledgeError(
            f"identity_keys defines keys for unknown entities: {sorted(unknown)}")
    return Knowledge(root=root, ontology=ontology, identity_keys=identity,
                     exclusion_reasons=reasons, taxonomy=taxonomy,
                     category_to_ddr=cat_to_ddr, sources=sources,
                     digest=_digest_dir(root))


@lru_cache(maxsize=8)
def _load_cached(root_str: str, digest: str) -> Knowledge:
    return _parse(Path(root_str))


# What makes a directory THE knowledge base, rather than merely a directory
# called "knowledge" — `src/knowledge/` is this package and must never be
# mistaken for the data.
_ROOT_MARKER = Path("ontology") / "entities.yaml"


def knowledge_root(start: Path | None = None) -> Path:
    """Find the knowledge base by walking up from `start` (default: this file).

    A candidate counts only if it actually holds the ontology; the Python
    package `src/knowledge/` shares the name and must not win."""
    here = Path(start) if start else Path(__file__).resolve()
    for parent in [here, *here.parents]:
        candidate = parent / KNOWLEDGE_DIRNAME
        if (candidate / _ROOT_MARKER).is_file():
            return candidate
    raise KnowledgeError(
        f"no {KNOWLEDGE_DIRNAME}/ base (containing {_ROOT_MARKER.as_posix()}) "
        f"found above {here}")


def load_knowledge(root: str | Path | None = None) -> Knowledge:
    """Load and validate knowledge/. Cached by content digest — an edit is seen
    immediately, an unchanged tree is never re-parsed."""
    base = Path(root) if root else knowledge_root()
    if not base.is_dir():
        raise KnowledgeError(f"knowledge root {base} is not a directory")
    return _load_cached(str(base), _digest_dir(base))
