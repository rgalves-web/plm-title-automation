"""The ownership arithmetic, read from the opinions and PROVED by Fraction.

The opinions print their own computations — owner by owner, as fraction chains:

    Roger Claxton Hanks, Jr. (Lease 31)    1/120 x 1/5 = 0.00166667
    D. F. Capital Investments, Inc.        2% x 1/64 x 1/2 x 87.5% = 0.00013672

and per-tract recaps that close to 1.00000000. This module transcribes nothing
and decides nothing: the vision pass transcribed, and here CODE evaluates every
printed expression exactly (`interest_formula`, `fractions.Fraction`) and
compares it with the decimal the examiner printed. Three outcomes only:

  VERIFIED   computed == printed at the opinion's own precision;
  MISMATCH   the examiner's arithmetic and ours disagree — a finding to show a
             human, never silently adopted either way;
  UNPARSED   the expression could not be read into arithmetic — a named
             PENDING, never a guess.

Sums per tract close exactly or the tract carries a named PENDING. Rounding a
recap into agreement is the one move this module refuses to know how to make.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from typing import Any

from src.knowledge.interest_formula import Blocking, parse_formula

# "NAME (Lease 31)   1/120 x 1/5 = 0.00166667"  — expression then printed value.
_INTEREST_LINE = re.compile(
    r"^(?P<name>[^=]{3,}?)\s{2,}(?P<expr>[0-9(\[][^=]*?)\s*=\s*"
    r"(?:(?P<midfrac>[0-9/,.\s]+)\s*=\s*)?(?P<printed>[01]?\.\d{6,8})\s*$")
# "Montie Julian Stewart    1/4 = 0.25000000"
_LEASE_REF = re.compile(r"\((Leases?\s+[0-9,\s and]+)\)")
# WI block rows: "EOG Resources, Inc.   0.50000000   0.40000000"
_WI_ROW = re.compile(
    r"^(?P<name>[A-Z][^0-9]{3,}?)\s{2,}(?P<op>[01]\.\d{6,8})\s+"
    r"(?P<rev>[01]\.\d{6,8})\s*$")
_RECAP_ROW = re.compile(
    r"^(?P<label>(?:Royalty|Net Revenue|Unleased|EOG Owned|Overriding|"
    r"Working Interest)[A-Za-z ()]*?):?\s{2,}(?P<value>[01]\.\d{6,8})\s*$")
_BARE_TOTAL = re.compile(r"^\s*(?P<value>[01]\.\d{6,8})\s*$")
_TRACT_HEAD = re.compile(r"^\s*(Tract \d+|All Tracts)\s*:?\s*$")
# The SECTION decides what an owner line's number IS: a mineral interest, a
# royalty product (MI x royalty), an unleased share, an override. Writing a
# ROYALTY-section product into the MI column is a faithful transcription of the
# wrong thing — found by the external harness comparing owner pairs.
_SECTION_HEAD = re.compile(
    r"^\s*(MINERALS? LESS EXECUTIVE RIGHTS|MINERALS?|ROYALTY"
    r"|UNLEASED INTERESTS?|OVERRIDING ROYALTY|EXECUTIVE RIGHTS)"
    r"(\s*\(Cont'?d\))?\s*:?\s*$", re.IGNORECASE)
_SECTION_KIND = {"MINERAL": "MI", "MINERALS": "MI",
                 "MINERALS LESS EXECUTIVE RIGHTS": "MI",
                 "MINERAL LESS EXECUTIVE RIGHTS": "MI",
                 # The right to LEASE, held separately from the mineral itself.
                 # Same owners, same page, different interest.
                 "EXECUTIVE RIGHTS": "EXEC",
                 "ROYALTY": "RI",
                 "UNLEASED INTEREST": "UNLEASED",
                 "UNLEASED INTERESTS": "UNLEASED",
                 "OVERRIDING ROYALTY": "ORRI"}
_ZONE_HEAD = re.compile(r"^\s*(From the surface[^:]*|Below the top[^:]*):?\s*$",
                        re.IGNORECASE)


def _normalise_expr(expr: str) -> str:
    """The examiners' notation, mapped onto interest_formula's grammar."""
    text = expr.replace("[", "(").replace("]", ")")
    text = text.replace("–", " less ").replace("−", " less ")
    text = re.sub(r"(?<=[)\d%])\s*-\s*(?=[( \d])", " less ", text)
    text = re.sub(r"(?<=[)\d%])\s*\+\s*(?=[( \d])", " plus ", text)
    return text


@dataclass
class OwnerInterest:
    name: str
    expression: str
    printed: str
    computed: Fraction | None
    verdict: str                    # VERIFIED | MISMATCH | UNPARSED
    leases: str = ""
    tract: str = ""
    page: int | None = None
    kind: str = "MI"                # MI | RI | UNLEASED | ORRI (by section)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "expression": self.expression,
                "printed": self.printed,
                "computed": str(self.computed) if self.computed is not None else None,
                "verdict": self.verdict, "leases": self.leases,
                "tract": self.tract, "page": self.page, "kind": self.kind}


@dataclass
class WIRow:
    name: str
    operating: str
    revenue: str
    tract: str = ""
    zone: str = ""
    page: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "operating": self.operating,
                "revenue": self.revenue, "tract": self.tract,
                "zone": self.zone, "page": self.page}


@dataclass
class TractRecap:
    tract: str
    components: dict[str, str] = field(default_factory=dict)
    closes: bool | None = None
    total: str = ""
    page: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"tract": self.tract, "components": dict(self.components),
                "closes": self.closes, "total": self.total, "page": self.page}


@dataclass
class Schedule:
    opinion: str
    owners: list[OwnerInterest] = field(default_factory=list)
    wi_rows: list[WIRow] = field(default_factory=list)
    recaps: list[TractRecap] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        out = {"VERIFIED": 0, "MISMATCH": 0, "UNPARSED": 0}
        for o in self.owners:
            out[o.verdict] += 1
        return out


def _verify(expr: str, printed: str) -> tuple[Fraction | None, str]:
    parsed = parse_formula(_normalise_expr(expr))
    if isinstance(parsed, Blocking):
        return None, "UNPARSED"
    places = len(printed.split(".")[1])
    printed_dec = Decimal(printed)
    computed_dec = (Decimal(parsed.value.numerator)
                    / Decimal(parsed.value.denominator))
    # The examiner rounded to their own precision; we compare there, exactly.
    if abs(computed_dec - printed_dec) <= Decimal(1) / (10 ** places) / 2:
        return parsed.value, "VERIFIED"
    return parsed.value, "MISMATCH"


def parse_schedule_blocks(opinion: str,
                          blocks: list[dict[str, Any]]) -> Schedule:
    sched = Schedule(opinion=opinion)
    tract = ""
    zone = ""
    section = "MI"                  # opinions open with the mineral ownership
    pending_recap: TractRecap | None = None
    for block in blocks:
        page = block.get("page")
        for raw in str(block.get("text") or "").splitlines():
            line = raw.rstrip()
            if not line.strip():
                continue
            m = _TRACT_HEAD.match(line)
            if m:
                tract = m.group(1)
                zone = ""
                if pending_recap and pending_recap.components:
                    sched.recaps.append(pending_recap)
                pending_recap = TractRecap(tract=tract, page=page)
                continue
            m = _ZONE_HEAD.match(line)
            if m:
                zone = m.group(1).strip()
                continue
            m = _SECTION_HEAD.match(line.strip())
            if m:
                key = " ".join(m.group(1).upper().split())
                section = _SECTION_KIND.get(key, section)
                continue
            m = _RECAP_ROW.match(line.strip())
            if m and pending_recap is not None:
                pending_recap.components[m.group("label").strip()] = \
                    m.group("value")
                continue
            m = _BARE_TOTAL.match(line)
            if m and pending_recap is not None and pending_recap.components:
                pending_recap.total = m.group("value")
                continue
            m = _WI_ROW.match(line.strip())
            if m and not _INTEREST_LINE.match(line.strip()):
                sched.wi_rows.append(WIRow(
                    name=" ".join(m.group("name").split()).rstrip(","),
                    operating=m.group("op"), revenue=m.group("rev"),
                    tract=tract, zone=zone, page=page))
                continue
            m = _INTEREST_LINE.match(line.strip())
            if m:
                name = " ".join(m.group("name").split())
                leases = ""
                lm = _LEASE_REF.search(name)
                if lm:
                    leases = lm.group(1)
                    name = _LEASE_REF.sub("", name).strip()
                computed, verdict = _verify(m.group("expr"), m.group("printed"))
                sched.owners.append(OwnerInterest(
                    name=name.rstrip(","), expression=m.group("expr").strip(),
                    printed=m.group("printed"), computed=computed,
                    verdict=verdict, leases=leases, tract=tract, page=page,
                    kind=section))
    if pending_recap and pending_recap.components:
        sched.recaps.append(pending_recap)

    for recap in sched.recaps:
        if not recap.total:
            # No printed closing total means this block is not a recap the
            # examiner closed (a WI sub-block, an ORRI table). Charging it
            # against 1.00000000 manufactures findings out of page layout.
            recap.closes = None
            continue
        total = sum(Decimal(v) for v in recap.components.values())
        stated = Decimal(recap.total)
        recap.closes = total == stated
        if not recap.closes:
            sched.findings.append(
                f"{sched.opinion} {recap.tract}: recap components sum to "
                f"{total}, stated {stated} — PENDING recap_nao_fecha")
    for o in sched.owners:
        if o.verdict == "MISMATCH":
            sched.findings.append(
                f"{sched.opinion} {o.tract or '?'} {o.name}: printed "
                f"{o.printed}, computed {o.computed} — MISMATCH to a human")
    return sched


def load_schedules(work_dir: str | Path) -> dict[str, Schedule]:
    import json

    data = json.loads((Path(work_dir) / "_ownership_schedules.json")
                      .read_text(encoding="utf-8"))
    names = {"a319": "T-O ORIG A-319 HILL CSL SURVEY BLKS 5 AND 6 318.3AC.PDF",
             "a669_50": "T-O ORIG W.S. SCARBOROUGH A-669 50AC.PDF",
             "a669_155": "T-O ORIG W.S. SCARBOROUGH A-669 155AC.PDF"}
    return {tag: parse_schedule_blocks(names.get(tag, tag), blocks)
            for tag, blocks in data.items()}


# ---------------------------------------------------------------------------
# Aggregation: owner interests -> the MI a LEASE carries
# ---------------------------------------------------------------------------
#
# The DDR's Ownership - Worksheet is per lease; the opinions compute per owner.
# The bridge is the lease reference the opinion prints beside each owner. Sums
# run in Fraction and are reported exactly: a lease whose owners' Fractions do
# not add to a representable value is a PENDING, never a rounded figure.

_LEASE_NOS = re.compile(r"\d+")


@dataclass
class LeaseInterest:
    lease_no: str                   # the opinion's own lease number
    tract: str
    total: Fraction
    printed_sum: str                # the sum of the printed decimals
    owners: list[str] = field(default_factory=list)
    verdicts: list[str] = field(default_factory=list)
    tracts: list[str] = field(default_factory=list)
    page: int | None = None

    @property
    def decimal(self) -> str:
        return f"{float(self.total):.8f}"

    @property
    def all_verified(self) -> bool:
        return all(v == "VERIFIED" for v in self.verdicts)

    def to_dict(self) -> dict[str, Any]:
        return {"lease_no": self.lease_no, "tract": self.tract,
                "total": str(self.total), "decimal": self.decimal,
                "printed_sum": self.printed_sum, "owners": self.owners,
                "verdicts": self.verdicts, "tracts": self.tracts,
                "page": self.page}


def _owner_key(name: str) -> str:
    """Owner identity WITHIN one opinion. Safe because a single examiner spells
    a person the same way on both schedules; never used across documents."""
    return re.sub(r"[^a-z]", "", str(name or "").lower())


def lease_interests(sched: Schedule) -> dict[str, LeaseInterest]:
    """lease no -> the exact Fraction mineral interest the lease captured.

    The link is not in the MINERALS section: opinions compute ownership first
    (who owns what) and only name a lease on the ROYALTY line, where the
    expression is that owner's MI times the lease royalty. So the chain is
    ROYALTY line -> owner -> that owner's MINERALS line, and the value written
    is the MINERAL interest, not the royalty product.

    A lease whose royalty owner has no minerals line — an owner who leased an
    interest the opinion accounts for elsewhere — yields nothing, deliberately:
    a blank with a reason beats a number nobody can trace."""
    minerals: dict[str, list[OwnerInterest]] = {}
    for o in sched.owners:
        if o.kind == "MI" and o.computed is not None:
            minerals.setdefault(_owner_key(o.name), []).append(o)

    # lease -> the distinct owners its royalty lines name. The SAME lease
    # appears once per tract in the royalty section, so the owners are collected
    # as a set before any arithmetic: adding an owner's undivided mineral
    # interest twice because the opinion computed his royalty in two tracts is
    # how a lease ends up holding more minerals than exist.
    by_lease: dict[str, dict[str, OwnerInterest]] = {}
    for o in sched.owners:
        if o.kind != "RI" or not o.leases:
            continue
        for lease_no in _LEASE_NOS.findall(o.leases):
            for mi_line in minerals.get(_owner_key(o.name), []):
                by_lease.setdefault(lease_no, {})[_owner_key(mi_line.name)] = mi_line

    out: dict[str, LeaseInterest] = {}
    for lease_no, owners in by_lease.items():
        # Only an UNAMBIGUOUS chain is written: one royalty line, one owner,
        # one minerals line. Where several owners resolve to one lease the
        # attribution is a question for a human, and a plausible sum is worse
        # than a declared blank (PR-10 governing rule).
        if len(owners) != 1:
            continue
        mi_line = next(iter(owners.values()))
        out[lease_no] = LeaseInterest(
            lease_no=lease_no, tract=mi_line.tract, total=mi_line.computed,
            printed_sum=mi_line.printed, owners=[mi_line.name],
            verdicts=[mi_line.verdict],
            tracts=[mi_line.tract] if mi_line.tract else [],
            page=mi_line.page)
    return out
