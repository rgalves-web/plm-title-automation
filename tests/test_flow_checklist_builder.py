"""Checklist builder: the method rendered as data (what / where / looks-like / why)."""
from __future__ import annotations

from src.flow.checklist_builder import ChecklistItem, build_checklist

_MANIFEST = {
    "title_opinions": [
        {"file_number": "T-O ORIG BRUMBAUGH A-122 212", "lessor": "BRUMBAUGH"},
    ],
    "reference_contracts": [
        {"file_number": "K1400170", "record_type": "FARMOUT AGREEMENT"},
    ],
    "leases": [{"lease_no": "0190122-007", "lessor": "BRADFORD"}],
    "wells": [{"well_name": "MAXWELL A UNIT #1H", "well_api": "42-337-34216"}],
}


def test_builds_an_item_per_manifest_entry():
    items = build_checklist(_MANIFEST)
    kinds = [i.kind for i in items]
    assert kinds.count("title_opinion") == 1
    assert kinds.count("contract") == 1
    assert kinds.count("lease_folder") == 1
    assert kinds.count("rrc_report") == 1


def test_every_item_renders_what_where_lookslike_why():
    for item in build_checklist(_MANIFEST):
        assert item.what and item.looks_like and item.why and item.where


def test_blocking_flags_follow_the_domain():
    by_kind = {i.kind: i for i in build_checklist(_MANIFEST)}
    assert by_kind["title_opinion"].blocking is False   # supplement controls; wanted-not-blocking
    assert by_kind["contract"].blocking is True         # recorded conveyance is required
    assert by_kind["rrc_report"].blocking is False      # absent -> MISSING, not blocking


def test_county_search_method_is_rendered_not_hidden():
    # A runsheet-instrument item must spell out the name+date-window method.
    item = ChecklistItem(id="x", kind="runsheet_instrument", what="y")
    from src.flow.checklist_builder import _TEMPLATES
    where = " ".join(_TEMPLATES["runsheet_instrument"]["where"]).lower()
    assert "name" in where and "abstract" in where and "never" in where


def test_item_roundtrip_dict():
    item = build_checklist(_MANIFEST)[0]
    back = ChecklistItem.from_dict(item.to_dict())
    assert back.id == item.id and back.why == item.why and back.blocking == item.blocking
