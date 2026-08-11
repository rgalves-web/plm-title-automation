"""The FETCH BRIEF and its gate — including the Josh B acceptance content.

The system does not fetch; it instructs. So the instruction is the deliverable,
and an incomplete instruction fails the round (FETCH_BRIEF_SPEC §0, §8).
"""
from __future__ import annotations

import pytest

from src.knowledge.fetch_brief import (
    ACTION_CONFIRM,
    ACTION_FETCH,
    ACTION_REQUEST,
    ACTION_UNFINDABLE,
    BriefError,
    BriefItem,
    FetchBrief,
    assert_brief_closes_the_round,
    carry_forward,
    render_markdown,
    validate_brief,
    validate_item,
    write_brief,
)
from src.knowledge.loader import load_knowledge

K = load_knowledge()


def _good_item(**kw) -> BriefItem:
    base = dict(
        id="lease_0000000-021",
        what="OGL Some Lessor, EOG lease 0000000-021, recorded Vol. 557 Pg. 240",
        where=["Drive: lease folder 0000000-021",
               "Drive: numerically adjacent sibling folders",
               "County records by Vol/Pg"],
        how="TexasFile: grantor `SOME LESSOR` + window 01/2011-06/2011",
        looks_like="3-year OGL, lessee EOG Resources; only valid if Vol. 557 Pg. 240 matches",
        unlocks=["Lease Review!L21 royalty", "Lease Review!L21 term"],
        already_searched=["round 4 (05/08): Drive by lessor name -> other units only"],
        blocking=False, action=ACTION_FETCH, source="county_records_portal")
    base.update(kw)
    return BriefItem(**base)


# --- the eight fields -------------------------------------------------------

def test_a_complete_item_passes():
    assert validate_item(_good_item(), K) == []


@pytest.mark.parametrize("field", ["what", "where", "how", "looks_like", "unlocks"])
def test_every_required_field_is_enforced(field):
    item = _good_item(**{field: [] if field in ("where", "unlocks") else ""})
    assert any(field in p for p in validate_item(item, K))


def test_a_where_with_no_concrete_location_fails():
    assert any("concrete" in p for p in validate_item(_good_item(where=["  "]), K))


# --- forbidden methods (spec §5, §8.3) --------------------------------------

def test_searching_by_abstract_is_a_failure():
    item = _good_item(how="TexasFile: search by abstract A-319 in Montague")
    problems = validate_item(item, K)
    assert any("FORBIDDEN" in p and "abstract" in p for p in problems)


def test_searching_the_drive_by_lessor_name_is_a_failure():
    item = _good_item(source="drive_plm",
                      how="Drive: search by lessor name Donald")
    assert any("FORBIDDEN" in p for p in validate_item(item, K))


def test_warning_against_a_forbidden_method_is_not_using_it():
    # A matcher that fires on MENTION rather than on PROPOSAL fails honest
    # briefs and teaches people to ignore it — the foreign-unit lesson again.
    for how in ("TexasFile: grantor `X` + date window. NEVER by abstract.",
                "by Vol/Pg; not by abstract, which drops recorded instruments"):
        assert validate_item(_good_item(how=how), K) == [], how


def test_a_request_that_explains_why_the_portal_is_useless_is_not_a_portal_search():
    item = _good_item(
        action=ACTION_REQUEST, source="third_party_request",
        how="email clerk@county.gov — $5 per search; the online portal has no "
            "pre-digital index, so this is a request rather than a search")
    assert validate_item(item, K) == []


def test_a_request_with_no_channel_is_treated_as_a_portal_search_and_fails():
    item = _good_item(action=ACTION_REQUEST, source="third_party_request",
                      how="look it up on the portal — $5")
    assert any("FORBIDDEN" in p for p in validate_item(item, K))


def test_the_correct_method_passes():
    item = _good_item(source="drive_plm",
                      how="Drive: by EOG lease number 0000000-021; then sibling folders")
    assert validate_item(item, K) == []


# --- requests are not searches (spec §7) ------------------------------------

def test_a_request_must_name_channel_and_cost():
    bare = _good_item(action=ACTION_REQUEST, source="third_party_request",
                      how="ask the clerk")
    problems = validate_item(bare, K)
    assert any("CHANNEL" in p for p in problems)
    assert any("COST" in p for p in problems)

    full = _good_item(action=ACTION_REQUEST, source="third_party_request",
                      how="email clerk@example.gov — $5 per case search")
    assert validate_item(full, K) == []


def test_a_confirm_item_must_say_what_conflicts():
    item = _good_item(action=ACTION_CONFIRM, conflict_with="")
    assert any("conflicts with" in p for p in validate_item(item, K))


# --- coverage: no orphan blank cell (the new invariant) ---------------------

def _brief(*items) -> FetchBrief:
    return FetchBrief(unit="SOME UNIT", generated="2026-08-11", items=list(items))


def test_a_blank_cell_with_no_item_is_an_orphan_and_fails():
    brief = _brief(_good_item())
    problems = validate_brief(brief, K, blank_cells=["Lease Review!F99"])
    assert any("orphan blank cell" in p for p in problems)


def test_a_blank_cell_with_a_terminal_reason_needs_no_item():
    brief = _brief(_good_item())
    assert validate_brief(brief, K, blank_cells=["Lease Review!F99"],
                          terminal_cells=["Lease Review!F99"]) == []


def test_a_blank_cell_owned_by_exactly_one_item_passes():
    brief = _brief(_good_item(unlocks=["Lease Review!F99"]))
    assert validate_brief(brief, K, blank_cells=["Lease Review!F99"]) == []


def test_a_blank_cell_claimed_by_two_items_fails():
    brief = _brief(_good_item(id="a", unlocks=["Lease Review!F99"]),
                   _good_item(id="b", unlocks=["Lease Review!F99"]))
    assert any("claimed by 2" in p for p in
               validate_brief(brief, K, blank_cells=["Lease Review!F99"]))


def test_the_gate_raises_so_a_round_cannot_close():
    with pytest.raises(BriefError, match="does not close the round"):
        assert_brief_closes_the_round(_brief(_good_item(how="")), K)


# --- ordering and grouping (spec §3, §4) ------------------------------------

def test_blocking_items_come_first_then_leverage():
    low = _good_item(id="low", unlocks=["a"])
    high = _good_item(id="high", unlocks=["a", "b", "c"])
    blocker = _good_item(id="blocker", blocking=True, unlocks=["z"])
    order = [i.id for i in _brief(low, high, blocker).ordered()]
    assert order == ["blocker", "high", "low"]


def test_unfindable_items_leave_the_brief():
    gone = _good_item(id="gone", action=ACTION_UNFINDABLE)
    assert [i.id for i in _brief(_good_item(), gone).ordered()] == ["lease_0000000-021"]


def test_items_group_by_source_so_one_portal_opens_once():
    grouped = _brief(_good_item(id="a", source="rrc"),
                     _good_item(id="b", source="rrc"),
                     _good_item(id="c", source="drive_plm")).by_source()
    assert len(grouped["rrc"]) == 2 and len(grouped["drive_plm"]) == 1


# --- negative knowledge accumulates (spec §6, §8.4) -------------------------

def test_an_unresolved_item_returns_with_its_history_grown():
    previous = _brief(_good_item(id="x", already_searched=["round 1: Drive"]))
    current = _brief(_good_item(id="x", already_searched=["round 2: TexasFile"]))
    merged = carry_forward(previous, current)
    assert merged.items[0].already_searched == ["round 1: Drive", "round 2: TexasFile"]


def test_a_resolved_item_leaves_the_brief():
    previous = _brief(_good_item(id="x"))
    current = _brief(_good_item(id="x"), _good_item(id="y"))
    assert [i.id for i in carry_forward(previous, current, resolved_ids=["x"]).items] == ["y"]


# --- rendering --------------------------------------------------------------

def test_the_markdown_carries_the_method_and_the_prohibition():
    md = render_markdown(_brief(_good_item(source="drive_plm",
                                           how="Drive: by EOG lease number")), K)
    assert "PLM Drive" in md
    assert "NEVER by lessor_name" in md
    assert "already searched" in md


def test_writing_the_brief_refuses_a_delivered_folder(tmp_path):
    from src.flow.deliverable_io import FrozenArtifactError
    frozen = tmp_path / "UNIT" / "SUBMISSION PLM"
    frozen.mkdir(parents=True)
    with pytest.raises(FrozenArtifactError):
        write_brief(_brief(_good_item()), frozen, K)


def test_writing_produces_both_renderings(tmp_path):
    y, m = write_brief(_brief(_good_item()), tmp_path, K)
    assert y.name == "fetch_brief.yaml" and m.suffix == ".md"
    assert "FETCH BRIEF" in m.read_text(encoding="utf-8")
    back = FetchBrief.from_dict(__import__("yaml").safe_load(
        y.read_text(encoding="utf-8")))
    assert back.items[0].id == "lease_0000000-021"
