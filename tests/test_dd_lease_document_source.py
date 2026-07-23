"""New-files lease-document source + TO-vs-document conflict merge (Collin closing)."""
from __future__ import annotations

from fractions import Fraction

from src.dd.dd_pipeline import _merge_lease_document_details, _values_conflict
from src.dd.lease_document_source import find_lease_document


def test_find_lease_document_by_lease_number_folder(tmp_path):
    folder = tmp_path / "0190122-005 (ROBERT W HRABOVSKY ET UX)" / "inner"
    folder.mkdir(parents=True)
    (folder / "LEASE.pdf").write_bytes(b"x")
    (folder / "LEASE MEMO - REC.TIF").write_bytes(b"x")
    found = find_lease_document(tmp_path, "0190122-005")
    assert found is not None and found.name == "LEASE.pdf"


def test_find_lease_document_absent_returns_none(tmp_path):
    assert find_lease_document(tmp_path, "0220344-013") is None


def test_merge_fills_empty_royalty_and_parses_ownership_fraction():
    rows = [{"lease_no": "0190122-005", "lessor": "Hrabovsky"}]
    details = {"0190122-005": {"_source": "LEASE.pdf (lease document)",
                               "royalty_text": "1/5 (20%) on oil, gas and casinghead gas"}}
    conflicts = _merge_lease_document_details(rows, details)
    assert conflicts == []                       # filled an empty, no conflict
    assert rows[0]["royalty_text"].startswith("1/5")
    assert rows[0]["royalty"] == Fraction(1, 5)  # Ownership Report col G (Fraction)
    assert rows[0]["source_lease_document"] == "LEASE.pdf (lease document)"


def test_merge_itemizes_genuine_conflict_and_prefers_instrument():
    rows = [{"lease_no": "0190122-008", "primary_term": "two (2) years"}]
    details = {"0190122-008": {"_source": "LEASE.pdf (lease document)",
                               "primary_term": "three (3) years"}}
    conflicts = _merge_lease_document_details(rows, details)
    assert len(conflicts) == 1
    assert "0190122-008" in conflicts[0] and "primary_term" in conflicts[0]
    assert rows[0]["primary_term"] == "three (3) years"  # recorded instrument wins


def test_values_conflict_ignores_substring_summaries():
    # A TO summary that is a substring of the fuller instrument text is not a conflict.
    assert not _values_conflict("Volume 476, Page 857", "VOL. 476 Page 857, Montague County, Texas")
    assert _values_conflict("1/4 royalty", "1/5 royalty")
