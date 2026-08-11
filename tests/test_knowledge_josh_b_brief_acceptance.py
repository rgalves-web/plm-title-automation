"""Checkpoint A acceptance for the FETCH BRIEF, against the written gabarito.

FETCH_BRIEF_SPEC §8 lists exactly what a cold Josh B brief must contain and what
it must never propose. The replay itself needs the classifier (F4) and the DPU
reading (F4/F5); what PR-3 can and must prove now is that the brief STRUCTURE
carries every one of those requirements, and that the gate rejects a brief that
gets them wrong.

So each requirement below is stated twice: the shape the brief must take, and
the failure the gate must catch if it does not.
"""
from __future__ import annotations

import pytest

from src.knowledge.fetch_brief import (
    ACTION_CONFIRM,
    ACTION_FETCH,
    ACTION_REQUEST,
    BriefItem,
    FetchBrief,
    render_markdown,
    validate_brief,
    validate_item,
)
from src.knowledge.loader import load_knowledge

K = load_knowledge()
TODAY = "2026-08-11"


# --- 1. the eight leases with no folder ------------------------------------

# From the gabarito: four in the DPU but absent from the XREF, four curative.
GABARITO_LEASES = {
    "0220604-018": ("Robert C. Donald, Jr.", "Vol. 506, Pg. 386"),
    "0220604-021": ("Mallory W. Joiner", "Vol. 557, Pg. 240"),
    "0220604-023": ("Jane L. Pendergast", "Vol. 562, Pg. 895"),
    "0220750-017": ("Robert C. Donald, Jr.", "Vol. 509, Pg. 137"),
    "0220604-022": ("Kramer Mineral Trust II", "Vol. 561, Pg. 757"),
    "0220604-024": ("Steven Dewitt Walker", "Vol. 567, Pg. 170"),
    "0221851-004": ("Methodist Home for Children (Waco)", "Vol. 530, Pg. 612"),
    "0222981-056": ("Choctaw Energy LP", "Vol. 581, Pg. 14"),
}


def _lease_item(lease: str) -> BriefItem:
    lessor, recording = GABARITO_LEASES[lease]
    return BriefItem(
        id=f"lease_{lease}",
        what=f"OGL {lessor}, EOG lease {lease}, recorded {recording}",
        where=[f"Drive: lease folder {lease}",
               "Drive: numerically adjacent sibling folders of the same series",
               f"County records portal by {recording}"],
        how=f"TexasFile: grantor `{lessor.split(',')[0].upper()}` + date window "
            f"around the lease date; or direct lookup by {recording}",
        looks_like=f"OGL, lessee EOG Resources; only ours if {recording} matches",
        unlocks=[f"Lease Review!{lease} royalty", f"Lease Review!{lease} term"],
        already_searched=["round 4 (05/08): Drive searched by lessor name — returned "
                          "only A-730 leases from other units, all outside the perimeter"],
        blocking=False, action=ACTION_FETCH, source="county_records_portal",
        effort="all eight carry a Vol/Pg — one sitting",
        origin="DPU Exhibit A x XREF cross-check")


def test_the_brief_carries_all_eight_leases_with_identity_and_method():
    brief = FetchBrief(unit="JOSH B UNIT", generated=TODAY,
                       items=[_lease_item(l) for l in GABARITO_LEASES])
    assert validate_brief(brief, K) == []
    assert len(brief.ordered()) == 8
    for item in brief.items:
        # Identity, not a nickname: the lease number AND its recording.
        assert "EOG lease" in item.what and "Vol." in item.what
        assert item.already_searched, "negative knowledge is mandatory"


def test_a_lease_item_without_its_recording_is_still_gated_on_the_other_fields():
    thin = BriefItem(id="lease_x", what="OGL somebody", where=[], how="",
                     looks_like="", unlocks=[])
    problems = validate_item(thin, K)
    assert len(problems) >= 4                    # where/how/looks_like/unlocks


# --- 2. the Unit Tract 1 blocker with its five alternative locations --------

TRACT_1_ALTERNATIVES = ["Josh A Unit", "Josh Unit", "Deaton / Deaton A",
                        "South Hills", "McCartney A"]


def _tract1_blocker() -> BriefItem:
    return BriefItem(
        id="to_unit_tract_1_a669_50ac",
        what="Original Title Opinion covering Unit Tract 1 — W. Scarbrough A-669, "
             "50 ac (FIRST TRACT of the Yentes deed, Vol. 217 Pg. 491)",
        where=["Drive: folders of neighbouring units that touch the same tract — "
               + ", ".join(TRACT_1_ALTERNATIVES),
               "Drive: lease folders 0221055-001 and 0221055-002",
               "Request from Collin/Trevor if EOG never ordered one"],
        how="Drive: by EOG lease number, then neighbouring-unit folders; the file "
            "is often filed under whichever unit ordered it",
        looks_like="Original T-O naming SCARBROUGH and 50 acres; not the A-811 "
                   "opinion, which covers the SECOND TRACT and is outside the unit",
        unlocks=["Ownership - Wells!O verified WI", "Ownership - Wells!Q verified NRI"],
        already_searched=["1st and 3rd rounds: folders 0221055-001/-002 re-checked, "
                          "identical content (same md5) — the opinion is not there"],
        blocking=True, action=ACTION_FETCH, source="drive_plm",
        origin="perimeter: Unit Tract 1 has no covering title opinion")


def test_the_tract_1_blocker_leads_the_brief_and_names_five_alternatives():
    brief = FetchBrief(unit="JOSH B UNIT", generated=TODAY,
                       items=[_lease_item("0220604-018"), _tract1_blocker()])
    assert validate_brief(brief, K) == []
    assert brief.ordered()[0].id == "to_unit_tract_1_a669_50ac"   # blocking first
    where = " ".join(brief.ordered()[0].where)
    for unit in TRACT_1_ALTERNATIVES:
        assert unit in where, unit


# --- 3. the four RRC items with the query path -----------------------------

RRC_ITEMS = {
    "w1": ("Form W-1 drilling permit", "Ownership - Wells!G Total Depth Drilled"),
    "completion": ("Form W-2/G-1 completion report", "Ownership - Wells!I Completion Date"),
    "plat": ("Well plat", "package Well Files/"),
    "production": ("Production report", "Ownership - Wells!K Gaps in Production"),
}


def _rrc_items() -> list[BriefItem]:
    return [BriefItem(
        id=f"rrc_{key}", what=f"{label} — Josh B Unit #1H, API 42-337-34773",
        where=["webapps.rrc.texas.gov", "gis.rrc.texas.gov for the plat"],
        how="ewaMain.do -> W-1 Query -> API 33734773 -> permit 730771",
        looks_like="RRC output carrying the API and the operator EOG Resources",
        unlocks=[unlocks], already_searched=[
            "08/10: the RRC site answered 'application error' on every attempt"],
        blocking=False, action=ACTION_FETCH, source="rrc",
        effort="four documents, one ~30 minute sitting")
        for key, (label, unlocks) in RRC_ITEMS.items()]


def test_the_four_rrc_items_group_into_one_sitting_with_the_query_path():
    brief = FetchBrief(unit="JOSH B UNIT", generated=TODAY, items=_rrc_items())
    assert validate_brief(brief, K) == []
    assert len(brief.by_source()["rrc"]) == 4
    md = render_markdown(brief, K)
    assert "ewaMain.do" in md and "33734773" in md
    # A portal outage is a state of the world, not a dead item.
    assert "application error" in md


# --- 4. the three Ector County probates: a REQUEST, not a search -----------

PROBATES = {"1449": "Charles F. Yentes",
            "3734-A": "J. C. McConnell",
            "16915-02": "Nellie M. McConnell"}


def _probate_items() -> list[BriefItem]:
    return [BriefItem(
        id=f"probate_{cause.replace('-', '_')}",
        what=f"Certified probate record, {name}, Cause {cause} — ECTOR County "
             "(not Montague: the estate was administered where the decedent lived)",
        where=["Ector County Clerk, Odessa TX"],
        how="email EctorCountyClerk.Probate@ectorcountytx.gov — $5 per case search; "
            "the online portal has no pre-digital index, so this is a request",
        looks_like=f"Certified copy naming {name} and Cause {cause}",
        # One curative line per cause: a blank cell is owned by exactly one item,
        # so three documents cannot hide behind a single shared row.
        unlocks=[f"PLM Title Review!Outstanding Curative — {name} (Cause {cause})"],
        already_searched=["08/10: Ector online portal searched — no results "
                          "(pre-digital index)"],
        blocking=False, action=ACTION_REQUEST, source="third_party_request",
        origin="T-O A-669 requirements, Tract 1 curative")
        for cause, name in PROBATES.items()]


def test_the_probates_are_requests_naming_county_channel_and_cost():
    brief = FetchBrief(unit="JOSH B UNIT", generated=TODAY, items=_probate_items())
    assert validate_brief(brief, K) == []
    for item in brief.items:
        assert item.action == ACTION_REQUEST
        assert "ECTOR" in item.what.upper() and "not Montague" in item.what
        assert "@" in item.how and "$" in item.how          # channel and cost
    assert set(PROBATES) == {i.id.split("probate_")[1].replace("_", "-")
                             for i in brief.items}


def test_a_probate_stated_as_a_portal_search_is_rejected():
    bad = _probate_items()[0]
    bad.how = "search the county portal for the cause number"
    assert any("FORBIDDEN" in p or "COST" in p for p in validate_item(bad, K))


# --- 5. the four vol/page conflicts are CONFIRM, not fetch -----------------

CONFLICTS = {
    "0220604-002": ("Vol. 427, Pg. 385", "Vol. 427, Pg. 685", "Lease & Mineral Schedule"),
    "0220953-005": ("Vol. 514, Pg. 412", "Vol. 515", "Lease & Mineral Schedule"),
    "0220953-006": ("Vol. 514, Pg. 414", "Vol. 515", "Lease & Mineral Schedule"),
    "0220953-007": ("Vol. 520, Pg. 2", "Vol. 520, Pg. 26", "Lease & Mineral Schedule"),
}


def _conflict_items() -> list[BriefItem]:
    return [BriefItem(
        id=f"confirm_{lease}",
        what=f"Recording conflict for lease {lease}: authority says {authority}",
        where=["Montague County real property records"],
        how=f"direct lookup by {authority}, then by {index_says}; whichever "
            "instrument actually exists settles it",
        looks_like="the recorded lease naming the same parties and date",
        unlocks=[f"Lease Review!{lease} recording"],
        already_searched=[], blocking=False, action=ACTION_CONFIRM,
        source="county_clerk_records", adopted_value=authority,
        conflict_with=f"{index} says {index_says}",
        origin="perimeter cross-check: authority vs index")
        for lease, (authority, index_says, index) in CONFLICTS.items()]


def test_the_four_conflicts_are_confirm_items_that_name_what_they_contradict():
    brief = FetchBrief(unit="JOSH B UNIT", generated=TODAY, items=_conflict_items())
    assert validate_brief(brief, K) == []
    assert len(brief.items) == 4
    for item in brief.items:
        assert item.action == ACTION_CONFIRM        # nothing is missing here
        assert item.conflict_with and item.adopted_value
    md = render_markdown(brief, K)
    assert "DDR provisionally adopted" in md


def test_a_confirm_item_that_does_not_say_what_it_contradicts_fails():
    item = _conflict_items()[0]
    item.conflict_with = ""
    assert any("conflicts with" in p for p in validate_item(item, K))


# --- the two prohibitions (spec §8.3) --------------------------------------

def test_proposing_a_search_by_abstract_fails_the_brief():
    item = _lease_item("0220604-021")
    item.how = "TexasFile: search Montague by abstract A-319 for the lease"
    problems = validate_brief(
        FetchBrief(unit="JOSH B UNIT", generated=TODAY, items=[item]), K)
    assert any("FORBIDDEN" in p and "abstract" in p for p in problems)


def test_proposing_a_drive_search_by_lessor_name_fails_the_brief():
    item = _tract1_blocker()
    item.how = "Drive: search by lessor name Stewart across the project"
    problems = validate_brief(
        FetchBrief(unit="JOSH B UNIT", generated=TODAY, items=[item]), K)
    assert any("FORBIDDEN" in p for p in problems)


# --- the whole brief together ----------------------------------------------

def test_the_full_josh_b_brief_passes_the_gate_and_covers_its_blanks():
    items = ([_lease_item(l) for l in GABARITO_LEASES] + [_tract1_blocker()]
             + _rrc_items() + _probate_items() + _conflict_items())
    brief = FetchBrief(unit="JOSH B UNIT", generated=TODAY, items=items)

    blanks = [cell for item in items for cell in item.unlocks]
    assert validate_brief(brief, K, blank_cells=blanks) == []

    assert len(items) == 8 + 1 + 4 + 3 + 4          # 20 items
    assert brief.ordered()[0].blocking              # the blocker leads
    sources = brief.by_source()
    assert set(sources) == {"county_records_portal", "drive_plm", "rrc",
                            "third_party_request", "county_clerk_records"}

    md = render_markdown(brief, K)
    # The priority section is an INDEX of ids, not a second copy of the items:
    # the first brief printed every blocking item in full here and again under
    # its source, and the operator scrolled past the same text twice.
    blocker = next(i for i in items if i.blocking)
    assert "block certification" in md
    assert blocker.id in md.split("\n\n")[1]        # named in the index…
    assert md.count(blocker.what) == 1              # …and written out exactly once
    assert "NEVER by abstract" in md                # the prohibition is printed
    assert "NEVER by lessor_name" in md


def test_an_orphan_blank_cell_fails_the_whole_brief():
    brief = FetchBrief(unit="JOSH B UNIT", generated=TODAY,
                       items=[_lease_item("0220604-018")])
    problems = validate_brief(brief, K, blank_cells=["Ownership - Wells!O3"])
    assert any("orphan blank cell" in p for p in problems)
