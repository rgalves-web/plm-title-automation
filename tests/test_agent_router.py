"""Deterministic intent routing (folder signatures + instruction hints)."""
from __future__ import annotations

from src.agent.router import route


def _touch(p):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x")


def test_routes_dd_from_folder_signatures(tmp_path):
    d = tmp_path / "BOWEN A UNIT"
    _touch(d / "DDR - Template (PLM).xlsx")
    _touch(d / "T-O ORIG BOWEN A-1449.pdf")
    _touch(d / "Lease to Well XREF.xlsx")
    r = route(d, "run confirmatory title for BOWEN A UNIT")
    assert r.pipeline == "dd_pipeline"
    assert r.unit_name == "BOWEN A UNIT"
    assert not r.needs_confirmation


def test_routes_mor_from_document_list_and_template(tmp_path):
    d = tmp_path / "Arapahoe"
    _touch(d / "document_list.xlsx")
    _touch(d / "runsheet_template.xlsx")
    _touch(d / "package.zip")
    r = route(d, "classify the document list and build the runsheet")
    assert r.pipeline == "mor_pipeline"
    assert not r.needs_confirmation


def test_ambiguous_or_empty_folder_needs_confirmation(tmp_path):
    d = tmp_path / "misc"
    _touch(d / "notes.txt")
    r = route(d, "do the thing")
    assert r.pipeline is None
    assert r.needs_confirmation
    assert "No recognizable" in r.reason or "Ambiguous" in r.reason


def test_unit_name_extracted_from_folder_when_absent_in_instruction(tmp_path):
    d = tmp_path / "MAXWELL A UNIT"
    _touch(d / "DDR Template.xlsx")
    _touch(d / "T0141486.pdf")
    r = route(d, "process this")
    assert r.pipeline == "dd_pipeline"
    assert r.unit_name == "MAXWELL A UNIT"
