"""FETCH BRIEF — the acquisition deliverable, and its gate.

The system does not fetch documents; the operator does. That trade only works
if the instruction is good enough to make the search mechanical, so the brief is
a first-class deliverable with a hard gate: a round carrying an incomplete brief
item does not close (FETCH_BRIEF_SPEC §0, §8).

Two renderings of one fact set: `fetch_brief.yaml` for the machine and
`FETCH BRIEF - <UNIT> - <date>.md` for a human to read on a phone. Both are
regenerated whole every round — the brief is a projection of the ledger and the
perimeter, never edited in place.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

# What the operator must DO with an item. The four are different actions, so
# they are never mixed in one list (spec §7).
ACTION_FETCH = "fetch"          # it exists somewhere; go get it
ACTION_REQUEST = "request"      # a third party must hand it over
ACTION_CONFIRM = "confirm"      # nothing is missing; something must be checked
ACTION_VERDICT = "verdict"      # the file is here; say what it is
ACTION_RESCAN = "rescan"        # the file is here and unreadable; open it by hand
ACTION_EXTRACT = "extract"      # the file is here and readable; WE have not read
                                # these fields off it yet. The work is the
                                # system's, not the operator's, and saying so is
                                # the difference between "a document is missing"
                                # and "I owe you a second pass".
ACTION_UNFINDABLE = "unfindable"  # declared not locatable — leaves for Missing Files
ACTIONS = (ACTION_FETCH, ACTION_REQUEST, ACTION_CONFIRM, ACTION_VERDICT,
           ACTION_RESCAN, ACTION_EXTRACT, ACTION_UNFINDABLE)

# Actions that assert a document IS NOT HERE. Only these carry the burden of
# proving absence, and absence is never proved by an unidentified file.
_ABSENCE_ACTIONS = (ACTION_FETCH, ACTION_REQUEST)
# The evidence value that can never support an absence claim.
UNPLACED = "unplaced"

# The eight fields every item owes (spec §2). Absence of any one is an invalid
# item, and an invalid item fails the round.
REQUIRED_FIELDS = ("id", "what", "where", "how", "looks_like",
                   "unlocks", "already_searched", "blocking")


class BriefError(AssertionError):
    """The brief does not satisfy its contract, so the round cannot close."""


# --- what "blocking" means -------------------------------------------------
#
# Blocking = the unit CANNOT BE CERTIFIED without it. It is not "this unlocks a
# cell" — every item unlocks a cell, so that reading makes the flag useless: a
# brief where 25 of 34 items are blocking has told the operator nothing about
# what to do first.
#
# It derives from what the missing document FEEDS. Verified WI/NRI and a tract's
# ownership cannot be stated at all while their basis is missing, so those
# block. An individual lease instrument does not: PLM works the runsheet before
# the lease review, and a lease review with a declared blank is a shippable
# deliverable (flow spec §1, step 14–15 — the exit condition is "evidenced or
# declared", never "100% filled").
BLOCKING_DESTINATIONS = frozenset({
    "ownership_report",        # a tract's ownership cannot be stated at all
    "ownership_wells",         # verified WI/NRI
    "perimeter",               # what is even in the unit
    "unit_and_pooling_agreements",
})


def blocks_certification(destinations: Iterable[str]) -> bool:
    """Does missing this stop the unit from being certified?"""
    return bool(BLOCKING_DESTINATIONS & {str(d) for d in destinations})


@dataclass
class BriefItem:
    id: str
    what: str                                   # full identity, not a nickname
    where: list[str] = field(default_factory=list)   # ranked, concrete locations
    how: str = ""                               # literal terms + query path
    looks_like: str = ""                        # and how to spot the false positive
    unlocks: list[str] = field(default_factory=list)  # DDR cells this frees
    already_searched: list[str] = field(default_factory=list)  # negative knowledge
    blocking: bool = False
    action: str = ACTION_FETCH
    source: str = ""                            # key into knowledge/rules/sources.yaml
    effort: str = ""
    origin: str = ""                            # what produced the item, with proof
    # `confirm` items: what the DDR provisionally adopted while the conflict stands
    adopted_value: str = ""
    conflict_with: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "what": self.what, "where": list(self.where),
            "how": self.how, "looks_like": self.looks_like,
            "unlocks": list(self.unlocks),
            "already_searched": list(self.already_searched),
            "blocking": self.blocking, "action": self.action,
            "source": self.source, "effort": self.effort, "origin": self.origin,
            "adopted_value": self.adopted_value, "conflict_with": self.conflict_with,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "BriefItem":
        return cls(**{k: v for k, v in d.items()
                      if k in cls.__dataclass_fields__})


@dataclass
class FetchBrief:
    unit: str
    generated: str                              # ISO date of the round
    items: list[BriefItem] = field(default_factory=list)
    round_no: int = 1

    # --- ordering: by leverage, never alphabetical (spec §3) ---------------
    def ordered(self) -> list[BriefItem]:
        def rank(it: BriefItem) -> tuple:
            return (
                0 if it.blocking else 1,        # blocks certification first
                -len(it.unlocks),               # then what frees the most cells
                0 if it.action == ACTION_FETCH else 1,   # cheap before costly
                it.id,
            )
        return sorted([i for i in self.items if i.action != ACTION_UNFINDABLE], key=rank)

    def by_source(self) -> dict[str, list[BriefItem]]:
        """One sitting, one source (spec §4) — so the operator opens a portal once."""
        grouped: dict[str, list[BriefItem]] = {}
        for item in self.ordered():
            grouped.setdefault(item.source or "unassigned", []).append(item)
        return grouped

    def to_dict(self) -> dict[str, Any]:
        return {"unit": self.unit, "generated": self.generated,
                "round": self.round_no,
                "items": [i.to_dict() for i in self.items]}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "FetchBrief":
        return cls(unit=d["unit"], generated=d.get("generated", ""),
                   round_no=d.get("round", 1),
                   items=[BriefItem.from_dict(i) for i in d.get("items", [])])


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------

# A method is forbidden when the brief PROPOSES it, not when it mentions it.
# "search by abstract A-319" teaches the wasteful method; "never by abstract"
# and "the portal has no index, so this is a request" warn against it. A matcher
# that cannot tell those apart fails honest briefs and trains people to ignore
# it — the same failure the foreign-unit stoplist had.
_PROPOSES = {
    "abstract": re.compile(
        r"(?<!never )(?<!not )(?<!nunca )\b(?:search|look|filter|query|busca[r]?)\b"
        r"[^.;]{0,40}\bby (?:the )?abstract\b", re.IGNORECASE),
    "lessor_name": re.compile(
        r"(?<!never )(?<!not )\b(?:search|look|query)\b[^.;]{0,30}"
        r"\bby (?:the )?lessor(?:'s)?(?: name)?\b", re.IGNORECASE),
}
_NEGATED = re.compile(r"\b(?:never|not|nunca|no)\b[^.;]{0,30}", re.IGNORECASE)
# A request that names a real channel is not being treated as a portal search,
# whatever the sentence happens to mention.
_HAS_CHANNEL = re.compile(r"@|\b(?:email|phone|mail|in person|counter)\b", re.IGNORECASE)


def _forbidden_hits(item: "BriefItem", knowledge: Any) -> list[str]:
    """Every forbidden method this item actually PROPOSES."""
    sources = getattr(knowledge, "sources", None)
    if sources is None:
        return []
    hits: list[str] = []
    source = item.source
    recipe = sources.get("sources", {}).get(source, {})
    forbidden = list(recipe.get("forbidden_methods") or [])
    # Global prohibitions apply to their named sources even when the item did
    # not name a recipe — a brief must never teach a session-wasting method.
    for entry in sources.get("globally_forbidden") or []:
        if source in (entry.get("applies_to") or []) or not source:
            forbidden.append(entry)

    how = item.how
    for entry in forbidden:
        method = str(entry.get("method", ""))
        if method == "portal_search":
            # The real defect is a request with no way to make it: if the item
            # names a channel, the word "portal" is context, not instruction.
            if item.action == ACTION_REQUEST and not _HAS_CHANNEL.search(how):
                hits.append(f"{method}: {entry.get('why', '')}".strip())
            continue
        pattern = _PROPOSES.get(method)
        if pattern is None:
            continue
        for match in pattern.finditer(how):
            prefix = how[max(0, match.start() - 30):match.start()]
            if _NEGATED.search(prefix):
                continue                     # "never by abstract" is a warning
            hits.append(f"{method}: {entry.get('why', '')}".strip())
            break
    return hits


def validate_item(item: BriefItem, knowledge: Any = None) -> list[str]:
    """Everything wrong with one item. Empty means it may ship."""
    problems: list[str] = []
    if item.action not in ACTIONS:
        problems.append(f"{item.id}: unknown action {item.action!r}")
    if item.action == ACTION_UNFINDABLE:
        return problems                        # leaves the brief; no field duty

    for name in REQUIRED_FIELDS:
        value = getattr(item, name)
        if name == "blocking":
            continue                           # a bool is always present
        if name == "already_searched":
            continue                           # may legitimately be empty on round 1
        if not value:
            problems.append(f"{item.id}: missing {name}")
    if item.where and not any(str(w).strip() for w in item.where):
        problems.append(f"{item.id}: `where` has no concrete location")
    if item.action == ACTION_CONFIRM and not item.conflict_with:
        problems.append(f"{item.id}: a confirm item must say what it conflicts with")
    if item.action == ACTION_REQUEST:
        # A request is not a search: it names a holder, a channel and a price,
        # or the operator cannot act on it (sources.yaml
        # third_party_request.requires_for_each_item).
        blob = " ".join([item.how, item.what, *item.where])
        if "@" not in blob and not re.search(r"\b(phone|mail|portal|in person|email)\b",
                                             blob, re.IGNORECASE):
            problems.append(f"{item.id}: a request must name the CHANNEL to use")
        # A price, "free", or an explicitly declared unknown. The third form
        # exists because a cold round often does NOT know a clerk's fee, and the
        # honest answer is "ask for it before ordering" — which is actionable.
        # Inventing a figure to satisfy a validator would be worse than silence;
        # silence itself still fails, which is the point of the check.
        if not re.search(r"\$|\bfree\b|\bno (?:fee|cost)\b|\bcusto\b"
                         r"|\bcost (?:is )?(?:not known|unknown)\b", blob,
                         re.IGNORECASE):
            problems.append(f"{item.id}: a request must state the COST (a figure, "
                            f"'free', or 'cost unknown — ask before ordering')")
    if knowledge is not None:
        for hit in _forbidden_hits(item, knowledge):
            problems.append(f"{item.id}: uses a FORBIDDEN method — {hit}")
    problems.extend(_absence_problems(item))
    return problems


def _absence_problems(item: BriefItem) -> list[str]:
    """A fetch/request asserts the document is NOT here. Prove it properly.

    `unplaced` means "I do not know what this is", and ignorance is not absence:
    the unidentified file in that folder may BE the document. Sending the
    operator to a courthouse for something already on their disk is the most
    expensive mistake the brief can make, so it is a gate failure, not a note.
    The right item for an unidentified file is a VERDICT ("say what this is"),
    which costs one look."""
    if item.action not in _ABSENCE_ACTIONS:
        return []
    evidence = " ".join([*item.already_searched, item.origin]).lower()
    if re.search(rf"\b{UNPLACED}\b", evidence):
        return [f"{item.id}: infers ABSENCE from {UNPLACED!r} — an unidentified "
                f"file may be the document itself. Emit a {ACTION_VERDICT!r} "
                f"item for it instead of a search."]
    return []


def validate_brief(brief: FetchBrief, knowledge: Any = None,
                   blank_cells: Iterable[str] = (),
                   terminal_cells: Iterable[str] = ()) -> list[str]:
    """The gate (spec §8). Empty list means the round may close.

    blank_cells: every blank DDR cell this round.
    terminal_cells: blanks whose reason is terminal (absent from the record, or
        declared unfindable) and which therefore owe no brief item.

    Coverage is the strict half: a blank cell that points at no item and has no
    terminal reason is an ORPHAN — the exact failure the invariant forbids,
    because it is a hole nobody is accountable for."""
    problems: list[str] = []
    seen: set[str] = set()
    for item in brief.items:
        if item.id in seen:
            problems.append(f"duplicate item id {item.id!r}")
        seen.add(item.id)
        problems.extend(validate_item(item, knowledge))

    covered = {cell for item in brief.items for cell in item.unlocks}
    terminal = set(terminal_cells)
    for cell in blank_cells:
        if cell in terminal:
            continue
        owners = [i.id for i in brief.items if cell in i.unlocks]
        if not owners:
            problems.append(
                f"orphan blank cell {cell}: no brief item and no terminal reason")
        elif len(owners) > 1:
            problems.append(
                f"blank cell {cell} is claimed by {len(owners)} items ({owners}) "
                "— exactly one must own it")
    return problems


def assert_brief_closes_the_round(brief: FetchBrief, knowledge: Any = None,
                                  blank_cells: Iterable[str] = (),
                                  terminal_cells: Iterable[str] = ()) -> None:
    problems = validate_brief(brief, knowledge, blank_cells, terminal_cells)
    if problems:
        raise BriefError(
            f"FETCH BRIEF for {brief.unit} does not close the round "
            f"({len(problems)} problem(s)):\n  - " + "\n  - ".join(problems))


# ---------------------------------------------------------------------------
# Carry-over between rounds (spec §8.4)
# ---------------------------------------------------------------------------

def carry_forward(previous: FetchBrief, current: FetchBrief,
                  resolved_ids: Iterable[str] = ()) -> FetchBrief:
    """A resolved item leaves; an unresolved one returns with its history grown.

    Negative knowledge is the field that saves the most time (spec §6), so it
    accumulates instead of being overwritten."""
    resolved = set(resolved_ids)
    prior = {i.id: i for i in previous.items}
    for item in current.items:
        old = prior.get(item.id)
        if old is None:
            continue
        merged = list(dict.fromkeys([*old.already_searched, *item.already_searched]))
        item.already_searched = merged
    current.items = [i for i in current.items if i.id not in resolved]
    return current


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

# The markdown is the OPERATOR's copy and has to fit on a screen; the YAML is the
# complete record. Long lists are summarised here and complete there.
MD_LIST_LIMIT = 4


def _compact(values: list[str]) -> str:
    if len(values) <= MD_LIST_LIMIT:
        return ", ".join(values)
    return (", ".join(values[:MD_LIST_LIMIT])
            + f" …and {len(values) - MD_LIST_LIMIT} more (see `fetch_brief.yaml`)")


def render_markdown(brief: FetchBrief, knowledge: Any = None) -> str:
    """The operator's copy: grouped by source, ordered by leverage."""
    lines = [f"# FETCH BRIEF — {brief.unit}",
             f"_Round {brief.round_no} · {brief.generated} · "
             f"{len(brief.ordered())} open items_", ""]

    # An INDEX, not a second copy of the items. The brief was unreadable when
    # every blocking item appeared here in full and again under its source: the
    # operator scrolled past the same text twice looking for the work.
    ordered = brief.ordered()
    blocking = [i for i in ordered if i.blocking]
    if blocking:
        lines += [f"**Do first ({len(blocking)} block certification):** "
                  + " · ".join(f"{i.id}" for i in blocking), ""]
    counts: dict[str, int] = {}
    for item in ordered:
        counts[item.action] = counts.get(item.action, 0) + 1
    if counts:
        lines += ["**By action:** " + " · ".join(
            f"{n} {action}" for action, n in sorted(counts.items(),
                                                    key=lambda kv: -kv[1])), ""]

    sources_doc = (getattr(knowledge, "sources", {}) or {}).get("sources", {})
    for source, items in brief.by_source().items():
        recipe = sources_doc.get(source, {})
        label = recipe.get("label", source)
        effort = next((i.effort for i in items if i.effort), "")
        head = f"## {label} — {len(items)} item(s)"
        if effort:
            head += f" · {effort}"
        lines.append(head)
        nav = recipe.get("navigation")
        if isinstance(nav, dict):
            for key, path in nav.items():
                lines.append(f"- path ({key}): `{path}`")
        elif nav:
            lines.append(f"- path: `{nav}`")
        for entry in recipe.get("forbidden_methods") or []:
            lines.append(f"- **NEVER by {entry.get('method')}** — {entry.get('why','').strip()}")
        lines.append("")
        for item in items:
            flag = " **[BLOCKING]**" if item.blocking else ""
            lines.append(f"### {item.what}{flag}")
            lines.append(f"- **action:** {item.action}")
            lines.append(f"- **where:**")
            for n, place in enumerate(item.where, 1):
                lines.append(f"  {n}. {place}")
            lines.append(f"- **how:** {item.how}")
            lines.append(f"- **recognise it:** {item.looks_like}")
            lines.append(f"- **unlocks:** {_compact(item.unlocks)}")
            if item.action == ACTION_CONFIRM:
                lines.append(f"- **conflict:** {item.conflict_with}")
                lines.append(f"- **DDR provisionally adopted:** {item.adopted_value}")
            if item.already_searched:
                # The full per-file negative knowledge lives in fetch_brief.yaml,
                # which is what carry_forward reads. Printing all 25 lines of it
                # here pushed the three items that need a human off the screen.
                lines.append("- **already searched (do not repeat):**")
                for note in item.already_searched[:MD_LIST_LIMIT]:
                    lines.append(f"  - {note}")
                extra = len(item.already_searched) - MD_LIST_LIMIT
                if extra > 0:
                    lines.append(f"  - _…and {extra} more, per file, in "
                                 f"`fetch_brief.yaml`_")
            if item.origin:
                lines.append(f"- _origin: {item.origin}_")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_brief(brief: FetchBrief, case_dir: str | Path,
                knowledge: Any = None) -> tuple[Path, Path]:
    """Write both renderings into the unit's case folder. Never into a
    delivered package — the frozen-artifact guard enforces that."""
    import yaml

    from src.flow.deliverable_io import assert_not_frozen

    case_dir = Path(assert_not_frozen(case_dir))
    case_dir.mkdir(parents=True, exist_ok=True)
    yaml_path = case_dir / "fetch_brief.yaml"
    md_path = case_dir / f"FETCH BRIEF - {brief.unit} - {brief.generated}.md"
    yaml_path.write_text(
        yaml.safe_dump(brief.to_dict(), sort_keys=False, allow_unicode=True),
        encoding="utf-8")
    md_path.write_text(render_markdown(brief, knowledge), encoding="utf-8")
    return yaml_path, md_path
