"""Tool wrappers: folder access / input enumeration (no pipeline invocation).

We test the *input mapping* — how a local folder is turned into the real
pipeline's arguments — without running the deterministic pipelines or any API.
"""
from __future__ import annotations

import zipfile

from src.agent.tools.dd_tool import enumerate_dd_inputs
from src.agent.tools.mor_tool import enumerate_mor_inputs
from src.agent.registry import default_registry


def test_dd_enumeration_finds_template_pdfs_and_extracts_zip(tmp_path):
    folder = tmp_path / "MAXWELL A UNIT"
    folder.mkdir()
    (folder / "DDR - Template (PLM).xlsx").write_bytes(b"x")
    (folder / "T-O ORIG.pdf").write_bytes(b"x")
    (folder / "Lease to Well XREF.xlsx").write_bytes(b"x")
    zpath = folder / "TOs.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("inside/LEASE.pdf", b"pdfbytes")

    docs, template = enumerate_dd_inputs(folder, tmp_path / "_x")
    assert template is not None and template.name.startswith("DDR")
    names = {p.name for p in docs}
    assert "T-O ORIG.pdf" in names
    assert "Lease to Well XREF.xlsx" in names  # non-template workbook -> document
    assert "LEASE.pdf" in names  # extracted from the zip
    assert "DDR - Template (PLM).xlsx" not in names  # template excluded from docs


def test_mor_enumeration_splits_doclist_template_package(tmp_path):
    folder = tmp_path / "Arapahoe"
    folder.mkdir()
    (folder / "document_list.xlsx").write_bytes(b"x")
    (folder / "runsheet_template.xlsx").write_bytes(b"x")
    (folder / "docs.zip").write_bytes(b"x")

    doclist, template, package = enumerate_mor_inputs(folder)
    assert doclist.name == "document_list.xlsx"
    assert template.name == "runsheet_template.xlsx"
    assert package.name == "docs.zip"


def test_default_registry_wires_both_pipelines():
    reg = default_registry()
    assert reg.names() == ["dd_pipeline", "mor_pipeline"]
    assert reg.get("dd_pipeline").param_schema  # has a schema
