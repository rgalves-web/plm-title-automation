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

from src.knowledge.fetch_brief import (ACTION_CONFIRM, ACTION_EXTRACT,
                                       ACTION_FETCH,
                                       ACTION_REQUEST, ACTION_RESCAN,
                                       ACTION_VERDICT, BriefItem, FetchBrief,
                                       blocks_certification, render_markdown,
                                       validate_brief, write_brief)
from src.knowledge.lease_disposition import (STATUS_ILLEGIBLE, STATUS_MEMO_ONLY,
                                             STATUS_OF_RECORD,
                                             STATUS_TERMS_SOURCED,
                                             STATUS_NO_INSTRUMENT,
                                             STATUS_NOT_IN_CORPUS,
                                             STATUS_OUTSIDE,
                                             STATUS_UNIDENTIFIED, dispose,
                                             summarise)
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


OPINIONS = (
    ("_to_a319_read.json", "schedule",
     "T-O ORIG A-319 HILL CSL SURVEY BLKS 5 AND 6 318.3AC.PDF", "May 21, 2010"),
)


DPU_EXHIBIT_A = Path("data/units/_josh_b_exhibitA.json")
DPU_NAME = '611.526.pdf (DPU JOSH B UNIT, Exhibit "A")'


def term_sources(knowledge: Any) -> list[dict[str, Any]]:
    """Every document that states OTHER entities' terms."""
    from src.knowledge.to_schedule import as_document

    out: list[dict[str, Any]] = []
    for filename, key, opinion, cert in OPINIONS:
        path = CASE / filename
        if not path.exists():
            continue
        blocks = json.loads(path.read_text(encoding="utf-8"))[key]
        ocr_path = CASE / filename.replace("_read.json", "_ocr.json")
        pages = (json.loads(ocr_path.read_text(encoding="utf-8"))
                 if ocr_path.exists() else None)
        out.append(as_document(opinion, blocks, cert_date=cert, ocr_pages=pages))

    # The unit designation itself: a recorded instrument printing lessor,
    # lessee, date and recording for every lease it pools.
    if DPU_EXHIBIT_A.exists():
        leases = json.loads(DPU_EXHIBIT_A.read_text(encoding="utf-8"))["leases"]
        out.append({
            "file": DPU_NAME, "classified_as": "dpu",
            "of_record": {"status": "recorded"}, "extracted": {},
            "proves": [{"recording_book_page": v.get("recording"),
                        "eog_lease_number": lease, "page": v.get("page"),
                        "quote": f'Exhibit "A": {lease} | {v.get("lessor")}',
                        "terms": {"lessor": v.get("lessor"),
                                  "lessee": "EOG Resources, Inc.",
                                  "instrument_date": v.get("date"),
                                  "recording": v.get("recording")}}
                       for lease, v in leases.items()]})
    return out


def dispositions(perimeter: Perimeter, by_lease: dict[str, list[dict[str, Any]]],
                 knowledge: Any) -> list[Any]:
    outside = {d.subject: d for d in perimeter.divergences
               if d.kind == "outside_perimeter"}
    extra = term_sources(knowledge)
    out = []
    for lease, recording in sorted(perimeter.leases.items()):
        div = outside.get(lease)
        out.append(dispose(
            lease, recording, by_lease.get(lease, []), knowledge,
            in_perimeter=div is None,
            outside_reason=(f"{div.index_says} || PROOF: {div.proof}" if div else ""),
            extra_sources=extra))
    return out


# ---------------------------------------------------------------------------
# Items
# ---------------------------------------------------------------------------

def _lease_cells(lease: str) -> list[str]:
    return [f"Lease Review!{lease}"]


# What each cell feeds — this, not "it unlocks a cell", is what decides
# `blocking` (fetch_brief.BLOCKING_DESTINATIONS).
LEASE_REVIEW_FEEDS = ("lease_review",)
PERIMETER_FEEDS = ("perimeter",)


def _grouped_fetch(disps: list[Any], item_id: str,
                   statuses: tuple[str, ...], title: str, origin: str,
                   already: list[str]) -> BriefItem | None:
    """One decision, one item — with the volume/page table inside it.

    Sixteen courthouse lookups are ONE sitting and ONE decision ("go pull these
    recordings"), not sixteen items. Splitting them buried the three findings
    that actually needed a human under twenty-five lines of the same sentence."""
    rows = [d for d in disps if d.status in statuses]
    if not rows:
        return None
    table = ["| lease | recording | what the folder already holds |",
             "|---|---|---|"]
    for d in sorted(rows, key=lambda x: x.lease):
        held = ", ".join(sorted({str(s.get("classified_as")) for s in d.sources})) \
            or "no folder in FILES/"
        table.append(f"| {d.lease} | {d.recording or '—'} | {held} |")
    return BriefItem(
        id=item_id,
        what=f"{title} — {len(rows)} lease(s), listed in the table below",
        where=[f"County Clerk real property records, {COUNTY} — direct lookup by "
               f"volume/page, one sitting",
               "PLM Drive: numerically adjacent folders of the same series"],
        how=("Pull each recording in the table directly; every one is known, so "
             "this is a lookup, not a search. In the Drive, check the sibling "
             "folders of the same series before the courthouse trip.\n\n"
             + "\n".join(table)),
        looks_like=('The recorded OGML naming EOG Resources, Inc. as lessee. '
                    'FALSE POSITIVE: the same lessor\'s lease in a neighbouring '
                    'unit — the pair (lease number, recording) must match '
                    'Exhibit "A"; neither field alone decides.'),
        # Per FIELD, not per row. "the lease is missing" and "the royalty is
        # missing on a lease that is present" are different holes with different
        # owners, and only field-level claims can tell them apart.
        unlocks=[c for d in rows for c in _blanks(d)],
        already_searched=already,
        # Lease Review does not block certification: PLM works the runsheet
        # first, and a declared blank ships.
        blocking=blocks_certification(LEASE_REVIEW_FEEDS),
        action=ACTION_FETCH, source="county_clerk_records",
        effort="one courthouse sitting for the whole table",
        origin=origin)


# The opinions whose requirements the gap-hunter reads, and the county their
# LAND sits in — which is the county a requirement's instrument does NOT have to
# be in, and the whole reason the county is extracted per requirement.
CURATIVE_SOURCES = (
    ("_to_a319_read.json", "requirements",
     "T-O ORIG A-319 HILL CSL SURVEY BLKS 5 AND 6 318.3AC.PDF", "A-319"),
    ("_to_a669_50_read.json", "requirements",
     "T-O ORIG W.S. SCARBOROUGH A-669 50AC.PDF", "A-669 Tract 1"),
)
LAND_COUNTY = "Montague"
CURATIVE_FEEDS = ("outstanding_curative",)


from src.knowledge.gap_hunter import feeds_of as gap_feeds


def live_requirements() -> list[Any]:
    """Every open requirement across the opinions we hold."""
    from src.knowledge.gap_hunter import hunt_requirements, parse_requirements

    gaps: list[Any] = []
    for filename, key, opinion, tag in CURATIVE_SOURCES:
        path = CASE / filename
        if not path.exists():
            continue
        blocks = json.loads(path.read_text(encoding="utf-8"))[key]
        gaps.extend(hunt_requirements(parse_requirements(blocks), opinion=opinion,
                                      land_county=LAND_COUNTY, tag=tag))
    return gaps


def _curative_items() -> list[BriefItem]:
    """Requirements grouped by WHO holds the answer — one sitting, one item.

    Grouping by county is not cosmetic. Three of these probates are of record in
    Ector County, ~350 miles from the land: they are one letter to one clerk,
    and mixing them into a Montague item would send the operator to a courthouse
    that has never heard of the decedents."""
    gaps = live_requirements()
    if not gaps:
        return []
    groups: dict[str, list[Any]] = {}
    for g in gaps:
        elsewhere = g.county and g.county.lower() != LAND_COUNTY.lower()
        # Remote records group by county (one letter, one clerk). Local curative
        # groups by KIND, because a quitclaim and an identity affidavit are
        # different signatures from different people — one item each keeps the
        # chase legible without going back to one item per row.
        # Remote records group by COUNTY — a different clerk is a different
        # letter. Local curative groups by what the requirement DECIDES:
        # everything that changes who owns a tract is one chase and one
        # blocker; the procedural rest is another. Splitting the local group any
        # finer produced nine items saying the same thing.
        if elsewhere:
            key = f"{g.county} County"
        elif "ownership_report" in gap_feeds(g.requirement_kind):
            key = "the parties — ownership curative"
        else:
            key = "the parties — procedural"
        groups.setdefault(key, []).append(g)

    out: list[BriefItem] = []
    for n, (holder, rows) in enumerate(sorted(groups.items()), start=1):
        remote = holder.endswith("County")
        table = ["| requirement | what is required | cause no. | leases |",
                 "|---|---|---|---|"]
        for g in sorted(rows, key=lambda x: x.subject):
            table.append(f"| {g.subject} | {g.detail[:220]} | "
                         f"{g.cause_no or '—'} | {', '.join(g.leases) or '—'} |")
        if remote:
            county = holder.replace(" County", "")
            how = (f"Write to the {county} County Clerk by e-mail or post and "
                   f"order certified copies, naming each cause number below. "
                   f"This is NOT {LAND_COUNTY} County: the land is in "
                   f"{LAND_COUNTY}; these records are of {county} because that "
                   f"is where the parties were, and asking {LAND_COUNTY} for "
                   f"them comes back empty. Cost unknown from the documents we "
                   f"hold — ask the clerk for the certified-copy fee before "
                   f"ordering, and record it so the next round states it.\n\n"
                   + "\n".join(table))
            where = [f"{county} County Clerk — probate records, by cause number, "
                     f"requested in writing (e-mail or post)"]
            source, action = "third_party_request", ACTION_REQUEST
        else:
            how = ("Obtain each instrument from the party named, or from the "
                   f"{LAND_COUNTY} County real property records where one is of "
                   "record. Every row is a separate signature to chase.\n\n"
                   + "\n".join(table))
            where = [f"County Clerk real property records, {COUNTY}",
                     "the parties named in the table, via PLM / the Seller"]
            source, action = "county_clerk_records", ACTION_FETCH
        kinds = {g.requirement_kind for g in rows}
        feeds = tuple({f for k in kinds for f in gap_feeds(k)})
        out.append(BriefItem(
            id=f"CURATIVE-{n:02d}",
            what=(f"Outstanding curative held by {holder} — {len(rows)} "
                  f"requirement(s) from the controlling title opinions"),
            where=where, how=how,
            looks_like=("Certified copies of the probate records / the executed "
                        "curative instruments named in each row."),
            unlocks=[f"Outstanding Curative!{g.subject.split(' —')[0]}"
                     for g in rows],
            already_searched=[f"{g.subject}: {g.proof[:150]}" for g in rows],
            # A requirement that changes WHO OWNS a tract feeds the ownership
            # tabs, and verified WI/NRI cannot be stated without it.
            blocking=blocks_certification(feeds),
            action=action, source=source,
            effort=("one letter for the whole list; the clerk's per-instrument "
                    "fee is the only cost" if remote
                    else "one sitting per party"),
            origin="COMMENTS AND REQUIREMENTS of the controlling opinions, read "
                   "requirement by requirement; the county comes from the "
                   "requirement's own text, never from the land's county"))
    return out


def build_items(perimeter: Perimeter, disps: list[Any]) -> list[BriefItem]:
    items: list[BriefItem] = []

    # --- the lease instruments: grouped by DECISION, not by row -------------
    absent = _grouped_fetch(
        [d for d in disps if d.route() == "fetch"
         and d.status not in (STATUS_UNIDENTIFIED, STATUS_ILLEGIBLE)],
        "LEASE-FETCH",
        (STATUS_NOT_IN_CORPUS, STATUS_NO_INSTRUMENT, STATUS_TERMS_SOURCED),
        "Recorded lease instruments not present in FILES/",
        origin=('every one is named in Exhibit "A" of ' + perimeter.authority
                + "; for the folders that exist, every document in them was read "
                  "AND identified, and none is the instrument"),
        already=[f"{d.lease}: " + ("; ".join(
            f"{Path(s['file']).name} = {s['classified_as']}" for s in d.sources)
            or "no folder in FILES/") for d in disps
            if d.route() == "fetch" and d.status not in (
                STATUS_OUTSIDE, STATUS_UNIDENTIFIED, STATUS_ILLEGIBLE)])
    if absent:
        items.append(absent)

    # --- unidentified: a VERDICT, never a search (rule 2) -------------------
    unknown = [d for d in disps if d.status == STATUS_UNIDENTIFIED]
    if unknown:
        table = ["| lease | file | why it is open |", "|---|---|---|"]
        for d in sorted(unknown, key=lambda x: x.lease):
            for s in d.sources:
                table.append(f"| {d.lease} | {Path(s['file']).name} | "
                             f"read, not identified |")
        items.append(BriefItem(
            id="VERDICT-UNPLACED",
            what=(f"Say what {sum(len(d.sources) for d in unknown)} unidentified "
                  f"file(s) are — they are already on disk"),
            where=[f"PLM Drive / FILES, in the lease folder named in the table"],
            how=("Open each file and give it a category. Do NOT fetch anything "
                 "for these leases until this is done: one of these files may BE "
                 "the instrument, and a courthouse trip for a document already on "
                 "the disk is the most expensive mistake this brief can make.\n\n"
                 + "\n".join(table)),
            looks_like="A decision, not a document.",
            unlocks=[c for d in unknown for c in _blanks(d)],
            already_searched=["the file was read; the reader could not identify it"],
            blocking=False, action=ACTION_VERDICT, source="drive_plm",
            effort="one look per file",
            origin="classified_as came back unidentified — absence cannot be "
                   "concluded while an unidentified file sits in the folder"))

    # --- illegible: re-scan, not a fetch (rule 5) --------------------------
    illegible = [d for d in disps if d.status == STATUS_ILLEGIBLE]
    if illegible:
        table = ["| lease | recording | copies on disk |", "|---|---|---|"]
        for d in sorted(illegible, key=lambda x: x.lease):
            table.append(f"| {d.lease} | {d.recording or '—'} | "
                         + ", ".join(Path(s["file"]).name for s in d.sources) + " |")
        items.append(BriefItem(
            id="RESCAN",
            what=(f"Re-scan or open by hand {len(illegible)} lease instrument(s) "
                  f"that ARE on disk and could not be read"),
            where=["PLM Drive / FILES, the copies named in the table",
                   f"County Clerk, {COUNTY} — only if the copies prove unusable"],
            how=("Open the copies directly (a TIF viewer, or print-and-read) "
                 "before anything else; if both copies are genuinely unusable, "
                 "THEN pull the recording at the courthouse.\n\n" + "\n".join(table)),
            looks_like="The instrument is here. This is a legibility problem, "
                       "not a missing document.",
            unlocks=[c for d in illegible for c in _blanks(d)],
            already_searched=["the file was opened and the read produced nothing "
                              "usable"],
            blocking=False, action=ACTION_RESCAN, source="drive_plm",
            effort="minutes per file",
            origin="the reader reported the document illegible"))

    # --- terms of record elsewhere: a DELIVERY, not a courthouse trip -------
    sourced = [d for d in disps if d.route() == "seller"]
    if sourced:
        table = ["| lease | recording | terms already filled, cited to |",
                 "|---|---|---|"]
        for d in sorted(sourced, key=lambda x: x.lease):
            cite = next(iter(d.proved_terms.values()))["cited_to"] \
                if d.proved_terms else "—"
            table.append(f"| {d.lease} | {d.recording or '—'} | "
                         f"{len(d.proved_terms)} terms — {cite} |")
        items.append(BriefItem(
            id="SELLER-DELIVERY",
            what=(f"Recorded instrument for {len(sourced)} lease(s) whose TERMS "
                  f"are already of record via the title opinion"),
            where=["Seller (EOG Resources, Inc.), via PLM — a file-delivery item"],
            how=("Request the instruments from the Seller through PLM by e-mail, "
                 "listing the lease numbers below. No cost. This is NOT a "
                 "courthouse trip: the opinion's lease summary already states "
                 "the terms, each cited to its page, so nothing is learned by "
                 "pulling the recording — only the document itself is owed.\n\n"
                 + "\n".join(table)),
            looks_like="The executed OGML matching the recording in the table.",
            # It unlocks only what is still BLANK. The terms the opinion already
            # proved are filled and cited — claiming them here would make the
            # item look bigger than it is and would double-own a filled cell.
            unlocks=[f"Lease Review!{d.lease}.{t}"
                     for d in sourced for t in sorted(d.unproved_terms)],
            already_searched=[f"{d.lease}: {d.note}" for d in sourced],
            blocking=blocks_certification(LEASE_REVIEW_FEEDS),
            action=ACTION_REQUEST, source="third_party_request",
            effort="one e-mail for the whole list",
            origin="knowledge/taxonomy title_opinion.proves_terms — an of-record "
                   "document that states a term is the source of that term"))

    # --- memo-only: the supervisor's rule ----------------------------------
    memo = [d for d in disps if d.status == STATUS_MEMO_ONLY]
    if memo:
        table = ["| lease | memorandum of record | terms it does not state |",
                 "|---|---|---|"]
        for d in sorted(memo, key=lambda x: x.lease):
            table.append(f"| {d.lease} | {d.recording or '—'} | "
                         + ", ".join(sorted(d.unproved_terms)) + " |")
        items.append(BriefItem(
            id="MISSING-LEASE",
            what=(f"Complete lease instrument for {len(memo)} lease(s) whose ONLY "
                  f"record is a memorandum"),
            where=["Seller (EOG Resources, Inc.), via PLM — the memorandum is of "
                   "record; the instrument it memorialises is not"],
            how=("Request from the Seller through PLM by e-mail, naming each lease "
                 "number and its memorandum recording. No portal search will find "
                 "it: an unrecorded instrument is in no index. No cost.\n\n"
                 + "\n".join(table)),
            looks_like="The executed OGML the memorandum refers to, carrying the "
                       "clause set the memorandum omits.",
            unlocks=[f"Lease Review!{d.lease}.{t}"
                     for d in memo for t in sorted(d.unproved_terms)],
            already_searched=[f"{d.lease}: memorandum read and of record at "
                              f"{d.sources[0]['file'].rsplit(chr(92), 1)[-1]}"
                              for d in memo if d.sources],
            blocking=False, action=ACTION_REQUEST, source="third_party_request",
            effort="one e-mail; turnaround is the Seller's",
            origin="the recorded memorandum proves the terms it states; the "
                   "lease is simultaneously a MISSING LEASE under Potential "
                   "Defects (categories.yaml lease_memorandum.dual_disposition)"))

    # --- scope: ONE decision, the proof stated ONCE ------------------------
    outside = [d for d in perimeter.divergences if d.kind == "outside_perimeter"
               and re.fullmatch(r"0\d{6}-\d{3}", d.subject)]
    if outside:
        series = sorted({s.subject.split("-")[0] for s in outside})
        items.append(BriefItem(
            id="SCOPE-OUTSIDE",
            what=(f"Confirm that the {', '.join(series)} series "
                  f"({len(outside)} leases) contributes ZERO acres to {UNIT}"),
            where=[f'{perimeter.authority} Exhibits "B" and "C" (held)',
                   f"Source deed Vol. 217, Pg. 491, Deed Records, {COUNTY} (held)"],
            how=("Read the proof below and confirm or reject it. Nothing to "
                 "fetch — the three documents that settle it are in hand.\n\n"
                 + outside[0].proof.replace(" || ", "\n\n")),
            looks_like="A confirmation, not a document.",
            unlocks=[f"Lease Review!{d.subject}" for d in outside],
            already_searched=["the three documents were read; the proof is "
                              "assembled"],
            blocking=blocks_certification(PERIMETER_FEEDS),
            action=ACTION_CONFIRM, source="drive_plm",
            effort="minutes — reading, not searching",
            adopted_value="outside the perimeter; zero acres",
            conflict_with='the leases ARE listed in Exhibit "A"',
            origin=f'Exhibit "A" lists them; Exhibits "B"/"C" and the source '
                   f"deed put their land outside the unit surveys"))

    # Non-lease scope divergences keep their own item: they are separate
    # decisions, and this one is NOT in the hand-built kit.
    for div in perimeter.divergences:
        if div.kind == "outside_perimeter" and not re.fullmatch(
                r"0\d{6}-\d{3}", div.subject):
            items.append(BriefItem(
                id="SCOPE-SPLIT-DEED",
                what=f"Confirm the split of {div.subject}",
                where=[f'{perimeter.authority} Exhibit "B" p.5 (held)',
                       f"Deed records, {COUNTY}"],
                how=(f"{div.authority_says}; {div.index_says}. Read the page and "
                     f"rule on it."),
                looks_like="A confirmation. NOT in the hand-built kit — verify "
                           "before relying on it.",
                unlocks=[f"Perimeter!{div.subject}"],
                already_searched=['Exhibit "B" p.5 was read in full'],
                blocking=blocks_certification(PERIMETER_FEEDS),
                action=ACTION_CONFIRM, source="county_clerk_records",
                effort="minutes",
                adopted_value="nothing adopted — the finding is new",
                conflict_with=div.index_says, origin=div.proof))

    # --- fields not yet read off documents we HOLD -------------------------
    held = [d for d in disps if d.status == STATUS_OF_RECORD and d.unproved_terms]
    if held:
        by_term: dict[str, int] = {}
        for d in held:
            for t in d.unproved_terms:
                by_term[t] = by_term.get(t, 0) + 1
        table = ["| field | leases still missing it |", "|---|---|"]
        for t, n in sorted(by_term.items(), key=lambda kv: -kv[1]):
            table.append(f"| {t} | {n} |")
        items.append(BriefItem(
            id="EXTRACT-FIELDS",
            what=(f"Second read of {len(held)} lease instrument(s) already on "
                  f"disk, for fields the first pass did not extract"),
            where=["PLM Drive / FILES — the instruments are already classified "
                   "and their paths are in the ledger"],
            how=("Nothing to fetch and nothing for you to do: this is the "
                 "system's own second pass over documents it already holds. It "
                 "is listed because these cells are blank, and a blank without "
                 "an owner is a hole nobody is accountable for.\n\n"
                 + "\n".join(table)),
            looks_like="A re-read, not a document.",
            unlocks=[c for d in held for c in _blanks(d)],
            already_searched=["the instrument was read once and classified; "
                              "these fields were not extracted from it"],
            blocking=blocks_certification(LEASE_REVIEW_FEEDS),
            action=ACTION_EXTRACT, source="drive_plm",
            effort="one pass over documents already on disk",
            origin="the instrument is of record and held; the field is blank "
                   "because it has not been read, not because it is missing"))

    items.extend(_curative_items())

    for div in perimeter.divergences:
        if div.kind == "conflicting_recording":
            items.append(BriefItem(
                id=f"CONFIRM-{div.subject}",
                what=f"Resolve the recording conflict for {div.subject}",
                where=[f"County Clerk real property records, {COUNTY}"],
                how=(f"Pull both references and see which instrument is the "
                     f"lease: {div.authority_says} vs {div.index_says}."),
                looks_like="Two volume/page references for one lease number.",
                unlocks=_lease_cells(div.subject),
                already_searched=[f"{div.index_name} was read"],
                blocking=blocks_certification(LEASE_REVIEW_FEEDS),
                action=ACTION_CONFIRM, source="county_clerk_records",
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


# Every column of the Lease Review a lease owes a value for. Naming them is what
# makes "94 blanks" mean something: a lease with no royalty and a lease with no
# instrument are not the same hole, and before this they counted the same.
LEASE_REVIEW_FIELDS = ("lessor", "lessee", "instrument_date", "recording",
                       "legal_description", "term", "royalty", "shut_in",
                       "depth_limitation", "pooling_clause", "bonus")


def _blanks(d: Any) -> list[str]:
    """Every blank this disposition leaves, PER FIELD (invariant 18).

    A blank whose cause is "nobody has identified the file" is still a blank and
    still owes an owner — it just owes a VERDICT item rather than a search."""
    if d.status == STATUS_OUTSIDE:
        return []
    if d.status == STATUS_OF_RECORD:
        # The instrument is here, and what it does NOT state is still a hole.
        # A missing royalty on a present lease is a field gap, not a document
        # gap, and it owes a field-level owner like any other blank.
        return [f"Lease Review!{d.lease}.{t}" for t in sorted(d.unproved_terms)]
    unproved = (sorted(d.unproved_terms) if d.unproved_terms
                else [f for f in LEASE_REVIEW_FIELDS
                      if f not in (d.proved_terms or {})])
    return [f"Lease Review!{d.lease}.{t}" for t in unproved]
