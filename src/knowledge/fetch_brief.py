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
ACTION_UNFINDABLE = "unfindable"  # declared not locatable — leaves for Missing Files
ACTIONS = (ACTION_FETCH, ACTION_REQUEST, ACTION_CONFIRM, ACTION_UNFINDABLE)

# The eight fields every item owes (spec §2). Absence of any one is an invalid
# item, and an invalid item fails the round.
REQUIRED_FIELDS = ("id", "what", "where", "how", "looks_like",
                   "unlocks", "already_searched", "blocking")


class BriefError(AssertionError):
    """The brief does not satisfy its contract, so the round cannot close."""


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
        if not re.search(r"\$|\bfree\b|\bno (?:fee|cost)\b|\bcusto\b", blob, re.IGNORECASE):
            problems.append(f"{item.id}: a request must state the COST (or that there is none)")
    if knowledge is not None:
        for hit in _forbidden_hits(item, knowledge):
            problems.append(f"{item.id}: uses a FORBIDDEN method — {hit}")
    return problems


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

def render_markdown(brief: FetchBrief, knowledge: Any = None) -> str:
    """The operator's copy: grouped by source, ordered by leverage."""
    lines = [f"# FETCH BRIEF — {brief.unit}",
             f"_Round {brief.round_no} · {brief.generated} · "
             f"{len(brief.ordered())} open items_", ""]

    blocking = [i for i in brief.ordered() if i.blocking]
    if blocking:
        lines += ["## Blocks certification — do these first", ""]
        for item in blocking:
            lines.append(f"- **{item.what}** ({item.id})")
            lines.append(f"  - unlocks: {', '.join(item.unlocks)}")
        lines.append("")

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
            lines.append(f"- **unlocks:** {', '.join(item.unlocks)}")
            if item.action == ACTION_CONFIRM:
                lines.append(f"- **conflict:** {item.conflict_with}")
                lines.append(f"- **DDR provisionally adopted:** {item.adopted_value}")
            if item.already_searched:
                lines.append("- **already searched (do not repeat):**")
                for note in item.already_searched:
                    lines.append(f"  - {note}")
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
