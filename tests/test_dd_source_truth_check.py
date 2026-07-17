"""Source-truth validation: every cell re-checked against the document it cites.

Structural rules verify FORM; these verify TRUTH. The discipline under test is
the three-way split: a value the source contradicts is a MISMATCH, a value the
source simply doesn't yield is UNVERIFIABLE — never a mismatch, because OCR is
lossy and an accusation on a bad scan is worse than an honest "cannot tell".
"""
from __future__ import annotations

from datetime import date
from fractions import Fraction

import openpyxl
import pytest

from src.dd.source_truth_check import (
    CONFIRMED,
    MISMATCH,
    UNVERIFIABLE,
    SourceIndex,
    check_date_against_xref,
    check_nri_arithmetic,
    check_recording_against_dpu,
    excel_serial_to_date,
    parse_loose_date,
    read_audit_cites,
    run_source_truth,
    states_value,
    truth_table,
)


# --- text matching ---------------------------------------------------------

def test_states_value_ignores_ocr_spacing_and_punctuation():
    assert states_value("Volume 405, Page 343, Montague County", "Volume 405 Page 343")
    assert states_value("EOG RESOURCES, INC.", "EOG Resources Inc")
    assert not states_value("Volume 405, Page 343", "Volume 412, Page 512")


# --- computable cross-checks ----------------------------------------------

def test_nri_equals_one_minus_royalty_minus_orri():
    assert check_nri_arithmetic(0.2, 0, 0.8)[0] == CONFIRMED
    assert check_nri_arithmetic(0.2, 0.017592593, 0.782407407)[0] == CONFIRMED


def test_wrong_nri_is_a_mismatch_against_its_own_inputs():
    outcome, expected = check_nri_arithmetic(0.25, 0, 0.9)
    assert outcome == MISMATCH
    assert expected == Fraction(3, 4)


def test_the_templates_own_nri_formula_is_confirmed_not_recomputed():
    # "=1-G8-W8" IS the rule; there is nothing for it to contradict.
    assert check_nri_arithmetic(0.2, 0, "=1-G8-W8")[0] == CONFIRMED


def test_nri_without_a_royalty_is_unverifiable_not_wrong():
    assert check_nri_arithmetic(None, 0, 0.8)[0] == UNVERIFIABLE


_DPU = {"0190122-001": ("402", "50"), "0220344-006": ("405", "343")}


def test_recording_matching_the_dpu_is_confirmed():
    assert check_recording_against_dpu("0190122-001", "402", "50", _DPU)[0] == CONFIRMED


def test_recording_differing_from_the_dpu_is_a_mismatch():
    # The real defect: Hulme's row carried John A Cox's recording (475/39).
    outcome, src = check_recording_against_dpu("0220344-006", "475", "39", _DPU)
    assert outcome == MISMATCH
    assert src == "Vol 405, Pg 343"


def test_lease_absent_from_the_dpu_is_unverifiable():
    assert check_recording_against_dpu("9999999-999", "1", "2", _DPU)[0] == UNVERIFIABLE


def test_excel_serial_and_loose_dates():
    assert excel_serial_to_date(39322) == date(2007, 8, 28)
    assert parse_loose_date("August 28, 2007") == date(2007, 8, 28)
    assert parse_loose_date("December 20, 2007") == date(2007, 12, 20)
    assert parse_loose_date("2 day of January, 2010") == date(2010, 1, 2)
    assert parse_loose_date("12/20/2007") == date(2007, 12, 20)
    assert parse_loose_date("no date here") is None


def test_contract_date_against_the_xref_serial():
    assert check_date_against_xref("August 28, 2007", 39322)[0] == CONFIRMED
    outcome, src = check_date_against_xref("August 29, 2007", 39322)
    assert outcome == MISMATCH and src == "2007-08-28"
    assert check_date_against_xref("unreadable", 39322)[0] == UNVERIFIABLE


# --- source resolution -----------------------------------------------------

def _docs(tmp_path, files: dict[str, str]):
    for name, body in files.items():
        (tmp_path / name).write_text(body, encoding="utf-8")
    return tmp_path


def test_source_index_resolves_a_reference_to_a_file(tmp_path):
    _docs(tmp_path, {"T-O SUPP LYNN W COX ET AL A-122.txt": "text"})
    index = SourceIndex([tmp_path])
    assert index.resolve("T-O SUPP LYNN W COX ET AL A-122") is not None


def test_source_index_ignores_a_page_cite_in_the_reference(tmp_path):
    _docs(tmp_path, {"T-O SUPP LYNN W COX.txt": "text"})
    index = SourceIndex([tmp_path])
    assert index.resolve("T-O SUPP LYNN W COX pp.5-6 (MINERALS)") is not None


def test_non_document_sources_never_resolve(tmp_path):
    index = SourceIndex([tmp_path])
    for reference in ("manifest", "dd_pipeline", "Lease to Well XREF", "formula"):
        assert index.resolve(reference) is None


def test_page_text_splits_on_form_feeds(tmp_path):
    _docs(tmp_path, {"doc.txt": "PAGE ONE\fPAGE TWO\fPAGE THREE"})
    index = SourceIndex([tmp_path])
    path = index.resolve("doc")
    assert "PAGE TWO" in index.page_text(path, 2)
    assert "PAGE ONE" not in index.page_text(path, 2)


# --- end to end ------------------------------------------------------------

def _wb(agreements: dict[str, object], audit: list[list]):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    ws = wb.create_sheet("Agreements")
    for coord, value in agreements.items():
        ws[coord] = value
    aud = wb.create_sheet("DD_Audit_Trail")
    aud.append(["Sheet", "Location", "Source Type", "Source Reference", "Confidence", "Extracted Text"])
    for row in audit:
        aud.append(row)
    return wb


def test_a_value_stated_in_the_cited_source_is_confirmed(tmp_path):
    _docs(tmp_path, {"ASMT.txt": "page one\fThis assignment from JOE BOB SMITH to EOG"})
    wb = _wb({"B4": "JOE BOB SMITH"},
             [["Agreements", "B4", "contract_instrument", "ASMT.TIF", 1, "grantor @ p.2"]])
    report = run_source_truth(wb, [tmp_path])
    hit = next(f for f in report.findings if f.cell == "B4")
    assert hit.outcome == CONFIRMED
    assert hit.source_page == "p.2"


def test_a_value_on_a_different_page_is_confirmed_but_noted(tmp_path):
    _docs(tmp_path, {"ASMT.txt": "JOE BOB SMITH appears here\fpage two"})
    wb = _wb({"B4": "JOE BOB SMITH"},
             [["Agreements", "B4", "contract_instrument", "ASMT.TIF", 1, "grantor @ p.2"]])
    report = run_source_truth(wb, [tmp_path])
    hit = next(f for f in report.findings if f.cell == "B4")
    assert hit.outcome == CONFIRMED and "NOT on the cited p.2" in hit.detail
    assert "names the wrong page" in hit.detail   # a bad cite is itself a defect


def test_a_value_absent_from_the_source_is_unverifiable_not_a_mismatch(tmp_path):
    # OCR is lossy; absence is not contradiction. This is the guard against the
    # over-reach that once produced thousands of false failures.
    _docs(tmp_path, {"ASMT.txt": "wholly unrelated text"})
    wb = _wb({"B4": "JOE BOB SMITH"},
             [["Agreements", "B4", "contract_instrument", "ASMT.TIF", 1, "grantor @ p.1"]])
    report = run_source_truth(wb, [tmp_path])
    hit = next(f for f in report.findings if f.cell == "B4")
    assert hit.outcome == UNVERIFIABLE
    assert report.truthful          # zero mismatches -> still shippable
    assert "not called a contradiction" in hit.detail


def test_a_cell_whose_source_is_not_a_document_is_unverifiable(tmp_path):
    wb = _wb({"B4": "EOG"},
             [["Agreements", "B4", "spreadsheet_row", "Lease to Well XREF", 1, ""]])
    report = run_source_truth(wb, [tmp_path])
    hit = next(f for f in report.findings if f.cell == "B4")
    assert hit.outcome == UNVERIFIABLE
    assert "not a document on disk" in hit.detail


def test_ownership_recording_mismatch_is_caught_end_to_end(tmp_path):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    ws = wb.create_sheet("Ownership Report")
    ws.cell(8, 2).value = "0220344-006"
    ws.cell(8, 11).value = "475"      # John A Cox's recording on Hulme's row
    ws.cell(8, 12).value = "39"
    aud = wb.create_sheet("DD_Audit_Trail")
    aud.append(["Sheet", "Location", "Source Type", "Source Reference", "Confidence", "Extracted Text"])
    report = run_source_truth(wb, [tmp_path], dpu_by_lease=_DPU)
    mismatch = next(f for f in report.mismatches if f.field_name == "Record Book/Page")
    assert "Vol 405, Pg 343" in str(mismatch.source_value)
    assert not report.truthful      # a contradicted value blocks the DDR


def test_truth_table_reports_per_sheet_counts(tmp_path):
    _docs(tmp_path, {"ASMT.txt": "JOE BOB SMITH"})
    wb = _wb({"B4": "JOE BOB SMITH", "B5": "NOT IN THE DOC"},
             [["Agreements", "B4", "contract_instrument", "ASMT.TIF", 1, "grantor @ p.1"],
              ["Agreements", "B5", "contract_instrument", "ASMT.TIF", 1, "form @ p.1"]])
    report = run_source_truth(wb, [tmp_path])
    table = truth_table(report)
    assert "Agreements" in table and "confirmed" in table
    assert report.per_sheet["Agreements"].confirmed == 1
    assert report.per_sheet["Agreements"].unverifiable == 1


def test_audit_cites_parse_cell_row_and_page():
    wb = _wb({}, [["Ownership Report", "row 17", "to_pdf", "T-O SUPP COX", 1, "MI @ p.5"],
                  ["Agreements", "B23", "contract_instrument", "ASMT.TIF", 1, "grantor @ p.1"]])
    cites = read_audit_cites(wb)
    assert cites[0].row == 17 and cites[0].cell is None and cites[0].page == 5
    assert cites[1].cell == "B23" and cites[1].row is None and cites[1].page == 1
