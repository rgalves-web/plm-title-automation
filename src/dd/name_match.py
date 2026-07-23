"""Deterministic person-name matching for title parties (Maxwell lessons item 5).

Fuzzy whole-string similarity (rapidfuzz token_sort_ratio) was the wrong tool for
this job: a lessor printed as "Marie Hulme" and the MINERALS owner "Marie Cantwell
Hulme" score 71 — below any threshold that also keeps "John A Cox" and "Richard T.
Cox" apart. Every extra middle name drags the score down, so real matches were
missed while the threshold stayed high enough to avoid false positives.

The rule here is structural, not statistical:

    Two person names refer to the same party when
      * the SURNAME is equal (case-insensitive), and
      * at least ONE given-name token matches, and
      * the identity suffix (Jr./Sr./II/III/IV) is the same.

Middle names and initials are ignored — they are evidence when present but never
required, so "Melba Sanderfer" matches "Melba Joy McGrew Sanderfer". A given-name
token matches when the tokens are equal or one is a prefix of the other (>= 3
chars), which resolves the common short-form printing "Pete" for "Peter".

Ambiguity is never resolved by picking the best score: when a query matches more
than one distinct candidate, the caller gets `ambiguous` and must leave the value
EMPTY and itemize it for review. Suffixes are identity-bearing (a father and son
are different people), so a differing or missing suffix blocks a match.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from rapidfuzz.distance import Levenshtein

from src.ownership import canonical_party_key

# Identity-bearing suffixes: preserved and required to agree (father vs son).
_SUFFIXES = {"JR", "SR", "II", "III", "IV", "V"}

# Role/wrapper tokens that describe a party's capacity, not their identity.
# "Estate of Mary June Croxton, deceased" and "Mary June Croxton Estate" are the
# same person; canonical_party_key already strips the trailing DECEASED/TRUSTEE.
_ROLE_TOKENS = {"ESTATE", "OF", "THE", "HEIRS", "HEIR", "DEC", "DECD",
                "INDIVIDUALLY", "AKA", "FKA", "NKA", "ET", "AL", "UX", "VIR"}

# A name containing any of these is an ENTITY, not a person: given/surname rules
# do not apply and we fall back to exact normalized equality.
_ENTITY_MARKERS = {"LLC", "LP", "LLP", "INC", "CORP", "CORPORATION", "COMPANY",
                   "CO", "TRUST", "BANK", "PARTNERSHIP", "LTD", "ASSOCIATION",
                   "MINERALS", "RESOURCES", "OIL", "GAS", "PROPERTIES", "ROYALTY",
                   "FOUNDATION", "CHURCH", "UNIVERSITY", "STATE"}

_MIN_PREFIX = 3  # "Pete" -> "Peter"; guards against "Jo" matching "John"
_MIN_OCR_TOKEN = 4  # one edit in a >=4-char name; "Marte" -> "Marie"


@dataclass(frozen=True)
class PersonName:
    given: tuple[str, ...] = ()      # real given tokens (>= 2 chars)
    initials: tuple[str, ...] = ()   # single-letter tokens — ignored for matching
    surname: str = ""
    suffix: str | None = None
    is_entity: bool = False
    normalized: str = ""

    @property
    def parsed(self) -> bool:
        return bool(self.surname or self.is_entity)


@dataclass
class NameMatchResult:
    """index into the candidate list, or None with a reason."""
    index: int | None = None
    ambiguous: list[str] = field(default_factory=list)
    reason: str = ""
    matched_on: str = ""   # "given_name" | "initial" — how the match was made

    @property
    def matched(self) -> bool:
        return self.index is not None


def parse_person_name(text: str | None) -> PersonName:
    """Split a printed party name into given tokens / surname / suffix."""
    if not text:
        return PersonName()
    key = canonical_party_key(str(text))
    if not key:
        return PersonName()
    # Drop possessive/punctuation remnants and split.
    tokens = [t for t in re.split(r"[^A-Z0-9']+", key) if t]
    if not tokens:
        return PersonName()

    if any(t in _ENTITY_MARKERS for t in tokens):
        return PersonName(is_entity=True, normalized=" ".join(tokens))

    suffix = None
    if tokens and tokens[-1] in _SUFFIXES:
        suffix = tokens[-1]
        tokens = tokens[:-1]
    # Role words carry no identity ("ESTATE OF ..." == "... ESTATE").
    tokens = [t for t in tokens if t not in _ROLE_TOKENS]
    if not tokens:
        return PersonName(suffix=suffix)

    surname = tokens[-1]
    rest = tokens[:-1]
    given = tuple(t for t in rest if len(t) > 1)
    initials = tuple(t for t in rest if len(t) == 1)
    return PersonName(given=given, initials=initials, surname=surname,
                      suffix=suffix, normalized=" ".join(tokens))


def _given_tokens_match(a: str, b: str) -> bool:
    if a == b:
        return True
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    return len(shorter) >= _MIN_PREFIX and longer.startswith(shorter)


def names_match(a: PersonName, b: PersonName) -> bool:
    """True when both names denote the same party under the structural rule."""
    if not a.parsed or not b.parsed:
        return False
    if a.is_entity or b.is_entity:
        # Entities do not have given/surnames — require exact normalized identity.
        return a.is_entity and b.is_entity and bool(a.normalized) and a.normalized == b.normalized
    if a.surname != b.surname:
        return False
    if a.suffix != b.suffix:
        return False  # Jr. and Sr. (or Jr. and unmarked) are different parties
    if not a.given or not b.given:
        # Nothing but initials on one side — not enough to identify a person.
        return False
    return any(_given_tokens_match(x, y) for x in a.given for y in b.given)


def names_match_by_initial(a: PersonName, b: PersonName) -> bool:
    """A WEAKER match: same surname and suffix, and an initial on one side is the
    first letter of a given name on the other ("W S Brumbaugh" ~ "Winston
    Brumbaugh").

    An initial is thin evidence on its own — "R. Cox" fits Richard, Robert and
    Reba equally — so this is only safe when exactly ONE candidate qualifies.
    match_person enforces that; do not call this to decide a match directly.
    """
    if not a.parsed or not b.parsed:
        return False
    if a.is_entity or b.is_entity:
        return False
    if a.surname != b.surname or a.suffix != b.suffix:
        return False
    for initials, givens in ((a.initials, b.given), (b.initials, a.given)):
        for initial in initials:
            if any(given.startswith(initial) for given in givens):
                return True
    return False


def names_match_by_ocr_variant(a: PersonName, b: PersonName) -> bool:
    """WEAKEST tier: same surname and suffix, and a given name differs by a
    single character — an OCR slip, not a different person.

    Motivated by a real case: the Cox supplement prints "Marie Cantwell Hulme"
    three times and "Marte Cantwell Hulme" once, in the MINERALS table — the one
    entry the extractor reads. Refusing that match drops a real owner's interest
    from the deliverable over a single mis-scanned letter.

    Guarded hard: the surname must match exactly (so the slip is confined to the
    given name), the token must be long enough that one edit is a small share of
    it, and — as with initials — match_person only accepts this when exactly one
    candidate qualifies.
    """
    if not a.parsed or not b.parsed or a.is_entity or b.is_entity:
        return False
    if a.surname != b.surname or a.suffix != b.suffix:
        return False
    for x in a.given:
        for y in b.given:
            if min(len(x), len(y)) >= _MIN_OCR_TOKEN and Levenshtein.distance(x, y) == 1:
                return True
    return False


def match_person(query: str | None, candidates: list[str]) -> NameMatchResult:
    """Match *query* against *candidates*, returning the single matching index.

    Three tiers, strongest first:
      1. a matching GIVEN NAME (equal or a >=3-char prefix) — decisive;
      2. failing that, a matching INITIAL — accepted only when exactly one
         candidate qualifies, since an initial alone cannot identify a person;
      3. failing that, a single-character OCR variant of a given name — same
         one-candidate rule.

    Returns index=None with a reason when nothing matches, or when two or more
    DISTINCT candidates match — the caller must then leave the value empty and
    itemize. Candidates that are merely repeated spellings of the same party
    (identical normalized name) do not count as ambiguity.
    """
    parsed_query = parse_person_name(query)
    if not parsed_query.parsed:
        return NameMatchResult(reason=f"{query!r} did not parse as a party name")

    parsed = [parse_person_name(c) for c in candidates]
    hits = [i for i, p in enumerate(parsed) if names_match(parsed_query, p)]
    matched_on = "given_name"
    if not hits:
        hits = [i for i, p in enumerate(parsed) if names_match_by_initial(parsed_query, p)]
        matched_on = "initial"
    if not hits:
        hits = [i for i, p in enumerate(parsed) if names_match_by_ocr_variant(parsed_query, p)]
        matched_on = "ocr_variant"
    if not hits:
        return NameMatchResult(reason=f"no candidate matches {query!r}")

    # Ambiguity means two DIFFERENT PEOPLE, decided by the same identity rule —
    # not by string inequality. An opinion lists the same party under several
    # spellings ("Winston Brumbaugh" in one tract, "Winston S. Brumbaugh" in
    # another); counting those as two parties would refuse a perfectly good match.
    clusters = _distinct_parties([parsed[i] for i in hits])
    if len(clusters) > 1:
        detail = " on an initial only" if matched_on == "initial" else ""
        return NameMatchResult(
            ambiguous=[candidates[i] for i in hits],
            reason=(f"{query!r} matches {len(clusters)} distinct parties{detail}: "
                    + "; ".join(sorted(candidates[i] for i in hits))
                    + " — resolve the identity before assigning a value"))
    return NameMatchResult(index=hits[0], matched_on=matched_on)


def _distinct_parties(names: list[PersonName]) -> list[list[PersonName]]:
    """Group names that denote the same party into one cluster each."""
    clusters: list[list[PersonName]] = []
    for name in names:
        for cluster in clusters:
            if names_match(name, cluster[0]) or name.normalized == cluster[0].normalized:
                cluster.append(name)
                break
        else:
            clusters.append([name])
    return clusters
