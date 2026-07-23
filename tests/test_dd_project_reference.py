"""Reference files resolve from the PROJECT folder, newest first — never from a
stale in-repo copy (standing rule)."""
from __future__ import annotations

from datetime import date

import pytest

from src.dd.project_reference import date_in_filename, find_reference, unit_folder


@pytest.mark.parametrize("name, expected", [
    ("Lease to Well and Contract XREF 06-16-2026 (1).xlsx", date(2026, 6, 16)),
    ("Well List - Updated 6.9.26 (1).xlsx", date(2026, 6, 9)),
    ("BKV Sync - 2026_07_09 15_12 CDT.txt", date(2026, 7, 9)),
    ("Lease to Well XREF.xlsx", None),
])
def test_dates_are_read_from_the_filename(name, expected):
    assert date_in_filename(name) == expected


def _touch(folder, name):
    p = folder / name
    p.write_bytes(b"x")
    return p


def test_newest_dated_version_wins(tmp_path):
    _touch(tmp_path, "Lease to Well and Contract XREF 05-01-2026.xlsx")
    newest = _touch(tmp_path, "Lease to Well and Contract XREF 06-16-2026 (1).xlsx")
    assert find_reference("xref", tmp_path) == newest


def test_dated_version_beats_undated(tmp_path):
    _touch(tmp_path, "Lease to Well XREF.xlsx")           # the stale export
    dated = _touch(tmp_path, "Lease to Well and Contract XREF 06-16-2026.xlsx")
    assert find_reference("xref", tmp_path) == dated


def test_original_beats_a_copy_of_the_same_date(tmp_path):
    _touch(tmp_path, "Copy of Lease to Well and Contract XREF 06-16-2026 (1).xlsx")
    original = _touch(tmp_path, "Lease to Well and Contract XREF 06-16-2026 (1).xlsx")
    assert find_reference("xref", tmp_path) == original


def test_missing_reference_returns_none_never_a_fallback(tmp_path):
    assert find_reference("xref", tmp_path) is None


def test_unknown_kind_is_an_error(tmp_path):
    with pytest.raises(ValueError):
        find_reference("nope", tmp_path)


def test_unit_folder_is_found_case_insensitively(tmp_path):
    (tmp_path / "MAXWELL A UNIT").mkdir()
    assert unit_folder("maxwell a unit", tmp_path).name == "MAXWELL A UNIT"
    assert unit_folder("BOWEN A UNIT", tmp_path) is None
