"""The Josh B round, cold: perimeter + dispositions -> the real FETCH BRIEF.

This is not a demo. It reads the DPU that is on disk, the corpus that is on
disk, and the two client indexes that are on disk, and it emits the brief the
operator would actually work from. It runs in a replay namespace and writes
nothing into the delivered unit tree (CLAUDE.md invariant 16).

The brief is a gate, not a report (FETCH_BRIEF_SPEC §8): a round carrying an
incomplete item does not close.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from src.knowledge.fetch_brief import (ACTION_CONFIRM, ACTION_FETCH,
                                       ACTION_REQUEST, BriefItem, FetchBrief,
                                       render_markdown, validate_brief, write_brief)
from src.knowledge.lease_disposition import (STATUS_MEMO_ONLY,
                                             STATUS_NO_INSTRUMENT,
                                             STATUS_NOT_IN_CORPUS,
                                             STATUS_OUTSIDE, dispose, summarise)
from src.knowledge.loader import load_knowledge
from src.knowledge.perimeter import Perimeter

CASE = Path("data/units/_josh_b_replay")
UNIT = "JOSH B UNIT"
COUNTY = "Montague County, Texas"


def load_round() -> tuple[Perimeter, dict[str, list[dict[str, Any]]], Any]:
    perimeter = Perimeter.from_dict(
        yaml.safe_load((CASE / "perimeter.yaml").read_text(encoding="utf-8")))
    by_lease: dict[str, list[dict[str, Any]]] = {}
    for rec in json.loads((CASE / "classifications.json").read_text(encoding="utf-8")):
        by_lease.setdefault(rec.get("lease", "?"), []).append(rec)
    return perimeter, by_lease, load_knowledge()


def dispositions(perimeter: Perimeter, by_lease: dict[str, list[dict[str, Any]]],
                 knowledge: Any) -> list[Any]:
    outside = {d.subject: d for d in perimeter.divergences
               if d.kind == "outside_perimeter"}
    out = []
    for lease, recording in sorted(perimeter.leases.items()):
        div = outside.get(lease)
        out.append(dispose(
            lease, recording, by_lease.get(lease, []), knowledge,
            in_perimeter=div is None,
            outside_reason=(f"{div.index_says} || PROOF: {div.proof}" if div else "")))
    return out


# ---------------------------------------------------------------------------
# Items
# ---------------------------------------------------------------------------

def _lease_cells(lease: str) -> list[str]:
    return [f"Lease Review!{lease}"]


def build_items(perimeter: Perimeter, disps: list[Any]) -> list[BriefItem]:
    items: list[BriefItem] = []
    n = 0

    def nid(prefix: str) -> str:
        nonlocal n
        n += 1
        return f"{prefix}-{n:02d}"

    for d in disps:
        if d.status == STATUS_NOT_IN_CORPUS:
            items.append(BriefItem(
                id=nid("LEASE"),
                what=(f"Oil, gas and mineral lease {d.lease}"
                      + (f", recorded {d.recording}" if d.recording else "")
                      + f' — listed in Exhibit "A" of the unit designation'),
                where=[f"PLM Drive: lease folder named {d.lease}",
                       f"PLM Drive: numerically adjacent folders in the "
                       f"{d.lease.split('-')[0]} series",
                       f"County Clerk real property records, {COUNTY}"
                       + (f" — direct lookup at {d.recording}" if d.recording else "")],
                how=(f"Drive: open the folder named exactly {d.lease}; if absent, "
                     f"open the sibling folders of the same series. Courthouse: "
                     + (f"go straight to {d.recording}."
                        if d.recording else
                        "search the grantor index by lessor name with a date "
                        "window around the lease date.")),
                looks_like=("A recorded OGML naming EOG Resources, Inc. as lessee, "
                            "with the lease number stamped or written on it. FALSE "
                            "POSITIVE: the same lessor's lease in a neighbouring "
                            "unit — the pair (lease number, recording) must match "
                            'Exhibit "A", neither field alone.'),
                unlocks=_lease_cells(d.lease),
                blocking=True, action=ACTION_FETCH, source="drive_plm",
                effort="immediate if the folder exists; otherwise one courthouse "
                       "lookup by volume/page",
                origin=f'Exhibit "A" of {perimeter.authority} lists it; no folder '
                       f'for it exists in FILES/'))

        elif d.status == STATUS_NO_INSTRUMENT:
            read = len(d.sources) or "the"
            items.append(BriefItem(
                id=nid("LEASE"),
                what=(f"Oil, gas and mineral lease {d.lease}"
                      + (f", recorded {d.recording}" if d.recording else "")
                      + " — the folder exists but holds no lease instrument"),
                where=[f"County Clerk real property records, {COUNTY}"
                       + (f" — direct lookup at {d.recording}" if d.recording else ""),
                       f"PLM Drive: numerically adjacent folders in the "
                       f"{d.lease.split('-')[0]} series"],
                how=(f"Courthouse: "
                     + (f"pull {d.recording} directly."
                        if d.recording else
                        "grantor index by lessor name, date window around the "
                        "lease date.")
                     + " Drive: check the sibling folders — a lease is often "
                       "filed one folder over."),
                looks_like=("The recorded OGML itself, not the lease data sheet, "
                            "not the bonus receipt, not the extension letter — "
                            f"{d.note or 'those are what the folder already holds'}."),
                unlocks=_lease_cells(d.lease),
                already_searched=[
                    f"PLM Drive folder {d.lease}: every document read and "
                    f"classified by content — " + "; ".join(
                        f"{Path(s['file']).name} = {s['classified_as']}"
                        for s in d.sources) or "folder empty"],
                blocking=True, action=ACTION_FETCH, source="county_clerk_records",
                effort="one courthouse lookup when the recording is known",
                origin=f"{d.note}"))

        elif d.status == STATUS_MEMO_ONLY:
            cite = d.defect["evidence"] if d.defect else ""
            items.append(BriefItem(
                id=nid("MISSING-LEASE"),
                what=(f"Complete lease instrument for {d.lease} — only the "
                      f"recorded MEMORANDUM is of record"
                      + (f" ({d.recording})" if d.recording else "")),
                where=["Seller (EOG Resources, Inc.), via PLM — the memorandum is "
                       "of record; the instrument it memorialises is not"],
                how=("Request from the Seller through PLM by e-mail, naming the "
                     f"lease number {d.lease} and the memorandum's recording"
                     + (f" ({d.recording})" if d.recording else "")
                     + ". No portal search will find it — an unrecorded "
                       "instrument is not in any index. No cost."),
                looks_like=("The executed OGML the memorandum refers to, with the "
                            "clause set the memorandum omits (royalty, pooling, "
                            "shut-in, depth limitation)."),
                unlocks=[f"Lease Review!{d.lease}.{term}"
                         for term in sorted(d.unproved_terms)],
                blocking=False, action=ACTION_REQUEST, source="third_party_request",
                effort="one e-mail; turnaround is the Seller's",
                origin=(f"the memorandum at {cite} is of record and proves "
                        f"{len(d.proved_terms)} term(s); it does not state "
                        f"{', '.join(sorted(d.unproved_terms)) or 'the remaining terms'}")))

    # Divergences the indexes raised
    for div in perimeter.divergences:
        if div.kind == "missing_from_index":
            continue                       # already an item via the disposition
        if div.kind == "outside_perimeter":
            items.append(BriefItem(
                id=nid("SCOPE"),
                what=(f"Confirm that {div.subject} contributes ZERO acres to "
                      f"{UNIT} and needs no further document"),
                where=[f'{perimeter.authority} Exhibits "B" and "C"',
                       "Source deed Vol. 217, Pg. 491, Deed Records, "
                       f"{COUNTY} (already held)"],
                how=("Read the proof already assembled and confirm it, or reject "
                     "it. Nothing to fetch: the three documents that settle it "
                     "are in hand."),
                looks_like="A confirmation, not a document.",
                unlocks=[f"Lease Review!{div.subject}"]
                        if re.fullmatch(r"0\d{6}-\d{3}", div.subject) else
                        [f"Perimeter!{div.subject}"],
                blocking=False, action=ACTION_CONFIRM, source="drive_plm",
                effort="minutes — reading, not searching",
                adopted_value="outside the perimeter; zero acres",
                conflict_with=div.authority_says,
                origin=div.proof))
        elif div.kind == "conflicting_recording":
            items.append(BriefItem(
                id=nid("CONFIRM"),
                what=f"Resolve the recording conflict for {div.subject}",
                where=[f"County Clerk real property records, {COUNTY}"],
                how=(f'Pull both references and see which instrument is the '
                     f'lease: {div.authority_says} vs {div.index_says}.'),
                looks_like="Two volume/page references for one lease number.",
                unlocks=_lease_cells(div.subject),
                blocking=False, action=ACTION_CONFIRM, source="county_clerk_records",
                effort="one lookup per reference",
                adopted_value=div.authority_says, conflict_with=div.index_says,
                origin=f'{div.index_name} disagrees with Exhibit "A"'))
    return items


def run(generated: str) -> dict[str, Any]:
    """`generated` is passed in, never taken from the clock — a replay that
    stamps itself with today's date is not a replay."""
    perimeter, by_lease, knowledge = load_round()
    disps = dispositions(perimeter, by_lease, knowledge)
    items = build_items(perimeter, disps)
    brief = FetchBrief(unit=UNIT, generated=generated, round_no=1, items=items)

    blank_cells = [c for d in disps for c in _blanks(d)]
    problems = validate_brief(brief, knowledge, blank_cells=blank_cells)

    (CASE / "dispositions.json").write_text(
        json.dumps([d.to_dict() for d in disps], indent=1, ensure_ascii=False),
        encoding="utf-8")
    yaml_path, md_path = write_brief(brief, CASE, knowledge=knowledge)
    return {"perimeter": perimeter, "dispositions": disps, "brief": brief,
            "problems": problems, "counts": summarise(disps),
            "yaml_path": yaml_path, "markdown_path": md_path,
            "blank_cells": blank_cells}


def _blanks(d: Any) -> list[str]:
    if d.status == STATUS_MEMO_ONLY:
        return [f"Lease Review!{d.lease}.{t}" for t in sorted(d.unproved_terms)]
    if d.status in (STATUS_NOT_IN_CORPUS, STATUS_NO_INSTRUMENT):
        return _lease_cells(d.lease)
    return []
