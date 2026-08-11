"""S5 GAP-HUNT — read the corpus the way an examiner reads it.

Not a search step. The gaps that matter are not "what is missing from a list";
they are what the documents we HOLD say about documents we do not:

  CITED BUT ABSENT   a title opinion names another opinion by date; a lease
                     recites a source deed; a requirement names an instrument to
                     be obtained. Each is a document the corpus points at and
                     does not contain.
  POST-CERT LEASE    a lease dated after every certification date we hold is
                     outside every opinion's scope — so either a supplemental
                     exists and we lack it, or nobody has examined that lease.
  LIVE REQUIREMENT   an opinion's requirements are not a list of chores; some are
                     satisfied by documents already in hand and some are open
                     risks. Telling them apart is the work.
  CONFLICT           two sources disagreeing is a finding with a named adopted
                     value, never a silent preference.
  INFERENCE          any conclusion not directly carried by a document is marked
                     INFERENCE and must survive an attack or be withdrawn.

The requirement pass carries one discipline that is easy to miss and expensive
to get wrong: **the county an instrument sits in is not the county of the land.**
Josh B's land is in Montague; three of its curative probates are of record in
ECTOR County, hundreds of miles away, because that is where the decedents lived.
An item that says "probate, Montague County" sends someone to the wrong
courthouse and comes back empty. So the county is extracted from the requirement
text itself, and when a requirement names a county that is not the land's, that
is the fact that travels into the brief.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# --- what a requirement is about -------------------------------------------
_COUNTY_RE = re.compile(r"\b([A-Z][a-zA-Z]+)\s+County\b")
_CAUSE_RE = re.compile(r"\b(?:Cause|Docket|Probate)\s*(?:No\.?|Number)?\s*"
                       r"([0-9][0-9A-Za-z\-]*)", re.IGNORECASE)
_LEASE_REF_RE = re.compile(r"\bLease\s+(\d{1,2})\b", re.IGNORECASE)
_VOLPAGE_RE = re.compile(r"\bVolume\s+(\d{2,4}),?\s+page\s+(\d{1,4})", re.IGNORECASE)

# Requirement subjects, from the vocabulary the opinions actually use. These
# label the item; they never decide whether it is satisfied.
_SUBJECTS = (
    ("probate", r"\bprobat|\bwill\b|\bestate of\b|\bheirship|\bdecedent"),
    ("quitclaim", r"\bquitclaim"),
    ("identity", r"\bone and the same\b|\bidentity\b|\bsame person\b|\baka\b"),
    ("nonproduction", r"\bnon-?production\b|\baffidavit of non"),
    ("release", r"\brelease\b"),
    ("assignment", r"\bassignment\b"),
    ("ratification", r"\bratification\b|\bratify"),
    ("consent", r"\bconsent\b"),
    ("possession", r"\bpossession\b|\btenant"),
    ("tax", r"\btax certificate\b|\bad valorem\b"),
    ("runsheet", r"\brunsheet\b"),
)
# Language that says the requirement is already answered.
_SATISFIED = re.compile(
    r"\bRequirement:\s*(None|No requirement|Advisory only|None, advisory)",
    re.IGNORECASE)
_ADVISORY = re.compile(r"advisory only", re.IGNORECASE)


# Which requirements change WHO OWNS a tract — those feed the ownership tabs and
# therefore block certification. The rest are procedural: they must be answered,
# but a declared blank ships without them.
OWNERSHIP_SUBJECTS = frozenset({"probate", "quitclaim", "identity",
                                "nonproduction", "ratification"})
PROCEDURAL_SUBJECTS = frozenset({"runsheet", "tax", "possession", "release",
                                 "consent", "other"})


def feeds_of(subject: str) -> tuple[str, ...]:
    """What a requirement of this kind feeds, for the blocking decision."""
    if subject in OWNERSHIP_SUBJECTS:
        return ("outstanding_curative", "ownership_report")
    return ("outstanding_curative",)


@dataclass
class Gap:
    kind: str                    # cited_but_absent | post_cert_lease |
                                 # live_requirement | conflict | inference
    subject: str
    detail: str
    proof: str                   # file + page + verbatim words
    county: str = ""             # where the instrument sits, when it is named
    cause_no: str = ""
    parties: str = ""
    leases: list[str] = field(default_factory=list)
    requirement_kind: str = ""
    inference: bool = False
    confidence: str = "stated"   # stated | inferred
    attack: str = ""             # what would refute it

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "subject": self.subject, "detail": self.detail,
                "proof": self.proof, "county": self.county,
                "cause_no": self.cause_no, "parties": self.parties,
                "leases": list(self.leases),
                "requirement_kind": self.requirement_kind,
                "inference": self.inference,
                "confidence": self.confidence, "attack": self.attack}


# ---------------------------------------------------------------------------
# Requirements
# ---------------------------------------------------------------------------

def parse_requirements(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Turn the read pages into requirement records. `blocks` are {page, text}."""
    out: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for block in blocks:
        for line in str(block.get("text") or "").splitlines():
            m = re.match(r"^\s*ITEM\s+(\d+[a-z]?)\s*$", line.strip(), re.IGNORECASE)
            if m:
                if current:
                    out.append(current)
                current = {"no": m.group(1), "page": block.get("page"),
                           "TITLE": "", "COMMENT": "", "REQUIREMENT": "",
                           "COUNTY": "", "CAUSE_NO": "", "LEASES": "",
                           "PARTIES": ""}
                continue
            if current is None:
                continue
            f = re.match(r"^(TITLE|COMMENT|REQUIREMENT|COUNTY|CAUSE_NO|LEASES|"
                         r"PARTIES):\s*(.*)$", line.strip())
            if f:
                current[f.group(1)] = f.group(2).strip()
                current["_last"] = f.group(1)
            elif line.strip() and current.get("_last"):
                current[current["_last"]] += " " + line.strip()
    if current:
        out.append(current)
    for r in out:
        r.pop("_last", None)
    return out


def subject_of(text: str) -> str:
    for name, pattern in _SUBJECTS:
        if re.search(pattern, text, re.IGNORECASE):
            return name
    return "other"


def counties_in(*texts: str) -> list[str]:
    found: list[str] = []
    for text in texts:
        for m in _COUNTY_RE.finditer(str(text or "")):
            name = m.group(1)
            if name.lower() in ("real", "deed", "said", "the") or name in found:
                continue
            found.append(name)
    return found


def hunt_requirements(requirements: list[dict[str, Any]], *, opinion: str,
                      land_county: str, tag: str = "") -> list[Gap]:
    """Which requirements are LIVE, and where each one's instrument sits.

    `tag` disambiguates the numbering: every opinion starts at Req 1, so
    "Req 1" alone names two different requirements in a unit with two
    controlling opinions."""
    gaps: list[Gap] = []
    for r in requirements:
        blob = " ".join([r.get("TITLE", ""), r.get("COMMENT", ""),
                         r.get("REQUIREMENT", "")])
        req_text = r.get("REQUIREMENT", "").strip()
        if not req_text or req_text.upper() in ("NONE", "NONE."):
            continue
        if _SATISFIED.search(f"Requirement: {req_text}") or _ADVISORY.search(req_text):
            continue

        stated = [c for c in counties_in(r.get("COUNTY", ""), blob)]
        # The county the INSTRUMENT sits in — which is not necessarily the
        # county of the land, and this is the whole point of extracting it.
        elsewhere = [c for c in stated if c.lower() != land_county.lower()]
        causes = r.get("CAUSE_NO", "").strip()
        causes = "" if causes.upper() in ("NONE", "") else causes
        causes = causes or ", ".join(
            m.group(1) for m in _CAUSE_RE.finditer(blob))
        leases = sorted({m.group(1) for m in _LEASE_REF_RE.finditer(blob)},
                        key=lambda x: int(x))
        subject = subject_of(blob)

        detail = req_text
        county = ", ".join(elsewhere) if elsewhere else (
            stated[0] if stated else "")
        if elsewhere:
            detail += (f"  [COUNTY: the instrument is of record in "
                       f"{', '.join(elsewhere)} County, NOT {land_county} — the "
                       f"land's county is not the record's county]")
        title = str(r.get("TITLE") or "").strip().rstrip(".")
        if not title or title.upper() == "NONE":
            # The reader found no heading. Naming the parties beats printing
            # "NONE" at the operator.
            title = str(r.get("PARTIES") or "").strip() or subject
        prefix = f"[{tag}] " if tag else ""
        gaps.append(Gap(
            kind="live_requirement",
            subject=f"{prefix}Req {r['no']} — {subject}: {title}",
            requirement_kind=subject,
            detail=detail, county=county, cause_no=causes,
            parties=r.get("PARTIES", ""), leases=[f"Lease {n}" for n in leases],
            proof=f"{opinion} p.{r.get('page')}: \"{blob[:220]}\"",
            confidence="stated"))
    return gaps


# ---------------------------------------------------------------------------
# Cited but absent
# ---------------------------------------------------------------------------

_CITES = (
    (r"[Tt]itle [Oo]pinion dated ([A-Z][a-z]+ \d{1,2}, \d{4})", "title opinion"),
    (r"[Ss]upplemental [Tt]itle [Oo]pinion[^.]{0,60}?"
     r"([A-Z][a-z]+ \d{1,2}, \d{4})", "supplemental title opinion"),
)


def hunt_citations(documents: list[dict[str, Any]], held_recordings: set[str],
                   *, texts: dict[str, list[str]] | None = None) -> list[Gap]:
    """Documents named inside documents that the corpus does not contain."""
    from src.knowledge.term_source import norm_recording

    gaps: list[Gap] = []
    seen: set[str] = set()
    for name, pages in (texts or {}).items():
        for page_no, text in enumerate(pages, start=1):
            for m in _VOLPAGE_RE.finditer(text or ""):
                key = norm_recording(f"{m.group(1)}.{m.group(2)}")
                if not key or key in held_recordings or key in seen:
                    continue
                seen.add(key)
                window = " ".join(text[max(0, m.start() - 130):m.start() + 90].split())
                gaps.append(Gap(
                    kind="cited_but_absent",
                    subject=f"Vol. {m.group(1)}, Pg. {m.group(2)}",
                    detail="cited inside a document we hold; not in the corpus",
                    proof=f"{name} p.{page_no}: \"{window}\"",
                    confidence="stated"))
            for pattern, what in _CITES:
                for m in re.finditer(pattern, text or ""):
                    key = f"{what}:{m.group(1)}"
                    if key in seen:
                        continue
                    seen.add(key)
                    gaps.append(Gap(
                        kind="cited_but_absent", subject=f"{what} of {m.group(1)}",
                        detail="named by date inside a document we hold",
                        proof=f"{name} p.{page_no}: \"{' '.join(text[max(0, m.start()-110):m.start()+110].split())}\"",
                        confidence="stated"))
    return gaps


# ---------------------------------------------------------------------------
# Leases outside every opinion's scope
# ---------------------------------------------------------------------------

def hunt_post_cert_leases(leases: dict[str, str], lease_dates: dict[str, str],
                          cert_dates: dict[str, str]) -> list[Gap]:
    """A lease dated after every cert date we hold was examined by nobody."""
    from datetime import datetime

    def parse(value: str):
        for fmt in ("%B %d, %Y", "%m/%d/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(str(value).strip(), fmt).date()
            except (ValueError, TypeError):
                continue
        return None

    latest = max((d for d in (parse(v) for v in cert_dates.values()) if d),
                 default=None)
    if latest is None:
        return []
    newest_from = max(cert_dates, key=lambda k: parse(cert_dates[k]) or _MIN)
    gaps: list[Gap] = []
    for lease, raw in sorted(lease_dates.items()):
        d = parse(raw)
        if d and d > latest:
            gaps.append(Gap(
                kind="post_cert_lease", subject=lease,
                detail=(f"dated {raw}, after the newest certification date we "
                        f"hold ({cert_dates[newest_from]}, {newest_from}). Either "
                        f"a supplemental opinion exists and we lack it, or no "
                        f"opinion has examined this lease."),
                proof=f'Exhibit "A" date {raw} vs {newest_from} cert '
                      f'{cert_dates[newest_from]}',
                confidence="stated"))
    return gaps


from datetime import date as _date
_MIN = _date(1, 1, 1)


# ---------------------------------------------------------------------------
# Inference discipline
# ---------------------------------------------------------------------------

def mark_inference(gap: Gap, attack: str) -> Gap:
    """An inference must name what would refute it, or it is not admissible."""
    gap.inference = True
    gap.confidence = "inferred"
    gap.attack = attack
    return gap


def survives(gap: Gap, refuted: bool, reason: str = "") -> Gap | None:
    """An inference that does not survive its attack is WITHDRAWN, not softened."""
    if not gap.inference:
        return gap
    if refuted:
        return None
    gap.detail += f"  [INFERENCE — survived attack: {reason}]" if reason else \
        "  [INFERENCE — survived attack]"
    return gap
