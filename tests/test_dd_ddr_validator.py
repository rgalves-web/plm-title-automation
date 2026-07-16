"""Deterministic DDR validator — the final gate.

Every fixture below is a defect that ACTUALLY SHIPPED in a Maxwell DDR and had to
be caught by hand. They are transcribed from that workbook's own correction log
(DD_Audit_Trail), so a passing test means the validator would have caught the
real thing:

  r111  Ownership Report · C815 · orphan "A" removed
  r109  Ownership - 1H · template shipped with Texaco/SMK/1991 sample data
  r110  PLM Title Review · r9-14 · Wiese Unit opinion (50.73ac, T0140007) — not Maxwell
  r103  Ownership Report · col V Cox rows · NRI formula =1-G-W was missing
  r107  Ownership Report · G32 · Loy D. Self royalty 1/5 (was blank)
  r108  Ownership Report · r37 · State lease MF-112592 royalty unknown (pending)
"""
from __future__ import annotations

import openpyxl
import pytest

from src.dd.ddr_validator import (
    FAIL,
    PENDING,
    UnitAllowlist,
    build_allowlist,
    console_summary,
    expected_sheet_set,
    validate_ddr,
    write_validation_sidecar,
)

_MAXWELL_LEASES = {"0190122-001", "0220344-013", "0220344-027", "0222854-000"}


def _allow() -> UnitAllowlist:
    return UnitAllowlist(
        unit_name="MAXWELL A UNIT",
        leases=set(_MAXWELL_LEASES),
        contracts={"K1400813", "K1400049"},
        title_opinions={"T0141486"},
        identity_tokens={"MAXWELL"},          # what "<name> Unit" may legitimately say
        foreign_unit_names={"WIESE", "ALAMO"},
    )


def _ddr(rows: list[list] | None = None, audit: list[list] | None = None,
         extra: dict[str, dict[str, object]] | None = None):
    """A minimal DDR: Ownership Report rows 8+, plus an audit trail."""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    ws = wb.create_sheet("Ownership Report")
    ws["A5"] = 208.9496
    for i, row in enumerate(rows or []):
        r = 8 + i
        for col, value in enumerate(row, start=1):
            if value is not None:
                ws.cell(r, col).value = value
    audit_ws = wb.create_sheet("DD_Audit_Trail")
    audit_ws.append(["Sheet", "Location", "Source Type", "Source Reference", "Confidence", "Extracted Text"])
    for a in (audit or []):
        audit_ws.append(a)
    for sheet_name, cells in (extra or {}).items():
        sheet = wb.create_sheet(sheet_name)
        for coord, value in cells.items():
            sheet[coord] = value
    return wb


def _own_row(lease="0220344-013", royalty=0.2, gross=140.9963, mi="=1/36",
             wi=0.84953704, nri="=1-G8-W8", orri=0):
    """A row shaped like the template: col2 lease, 7 royalty, 18 gross,
    19 MI, 20 WI, 22 NRI, 23 ORRI."""
    row = [None] * 24
    row[1] = lease
    row[6] = royalty
    row[17] = gross
    row[18] = mi
    row[19] = wi
    row[21] = nri
    row[22] = orri
    return row


def _audited(rows=("row 8",)):
    return [["Ownership Report", r, "to_pdf", "T-O SUPP LYNN W COX"] for r in rows]


# --- coverage accounting ---------------------------------------------------

def test_every_populated_cell_is_counted_and_checked():
    wb = _ddr([_own_row()], _audited())
    report = validate_ddr(wb, _allow())
    assert report.total_cells > 0
    assert report.checked_cells == report.total_cells
    assert report.reconciled
    assert f"{report.checked_cells} of {report.total_cells} cells checked" in report.summary()


def test_coverage_is_reported_per_sheet():
    wb = _ddr([_own_row()], _audited())
    report = validate_ddr(wb, _allow())
    sheets = {c.sheet for c in report.coverage}
    assert {"Ownership Report", "DD_Audit_Trail"} <= sheets
    assert all(c.reconciled for c in report.coverage)


def test_a_run_that_does_not_reconcile_is_not_ready():
    wb = _ddr([_own_row()], _audited())
    report = validate_ddr(wb, _allow())
    report.coverage[0].visited -= 1          # simulate a skipped cell
    assert not report.reconciled
    assert not report.ready
    assert "COVERAGE DID NOT RECONCILE" in report.summary()


# --- the real defects ------------------------------------------------------

def test_catches_the_C815_orphan():
    # r111: a lone "A" stranded at C815 with the body ending at row 37.
    wb = _ddr([_own_row()], _audited())
    wb["Ownership Report"]["C815"] = "A"
    report = validate_ddr(wb, _allow())
    orphans = [f for f in report.failures if f.rule == "orphan_cell"]
    assert any(f.cell == "C815" and f.value == "A" for f in orphans), report.summary()
    assert not report.ready


def test_catches_texaco_template_sample_data():
    # r109: the PLM template ships with Texaco/SMK/1991 sample rows.
    wb = _ddr([_own_row()], _audited(),
              extra={"Ownership - 1H (No FO Option)": {"B4": "TEXACO INC.", "C4": "SMK 1991"}})
    report = validate_ddr(wb, _allow())
    hits = [f for f in report.failures if f.rule == "template_sample_data"]
    assert len(hits) >= 1
    assert any("TEXACO" in f.expected.upper() for f in hits)
    assert not report.ready


def test_catches_the_wiese_foreign_unit_opinion():
    # r110: a Wiese Unit opinion (T0140007) in a Maxwell deliverable.
    wb = _ddr([_own_row()], _audited(),
              extra={"PLM Title Review": {"A9": "Wiese Unit opinion 50.73ac", "B9": "T0140007"}})
    report = validate_ddr(wb, _allow())
    leaks = [f for f in report.failures if f.rule == "foreign_unit_leakage"]
    assert any("WIESE" in f.expected.upper() for f in leaks), [f.describe() for f in leaks]
    assert any("T0140007" in f.expected for f in leaks)
    assert not report.ready


def test_catches_blank_nri_on_a_row_with_wi():
    # r103: the =1-G-W formula was missing on the Cox rows.
    wb = _ddr([_own_row(nri=None)], _audited())
    report = validate_ddr(wb, _allow())
    assert any(f.rule == "nri_sanity" and f.cell == "V8" for f in report.failures)
    assert not report.ready


def test_catches_missing_royalty_on_an_active_wi_row():
    # r107: Loy D. Self's Cox lease had no royalty until it was read off p.8.
    wb = _ddr([_own_row(lease="0220344-027", royalty=None)], _audited())
    report = validate_ddr(wb, _allow())
    assert any(f.rule == "royalty_presence" and f.severity == FAIL for f in report.failures)
    assert not report.ready


def test_missing_royalty_with_a_recorded_reason_is_pending_not_a_failure():
    # r108: the State lease MF-112592 is not in the file — a known gap, not a defect.
    wb = _ddr([_own_row(lease="0222854-000", royalty=None)],
              _audited() + [["Ownership Report", "G8", "flagged_pending",
                             "State lease MF-112592 not in file; royalty unknown"]])
    report = validate_ddr(wb, _allow())
    royalty = [f for f in report.findings if f.rule == "royalty_presence"]
    assert royalty and all(f.severity == PENDING for f in royalty)
    assert not [f for f in report.failures if f.rule == "royalty_presence"]


def test_catches_mi_flattened_across_a_tract():
    # 13 Cox rows all carrying 5/36 sum to 1.81 — the flattening bug.
    rows = [_own_row(lease=f"022034{i:01d}-013", mi="=5/36") for i in range(9)]
    wb = _ddr(rows, [["Ownership Report", f"row {8+i}", "to_pdf", "T-O"] for i in range(9)])
    report = validate_ddr(wb, _allow())
    assert any(f.rule == "mi_per_tract_sum" for f in report.failures)


def test_catches_a_foreign_lease_number():
    wb = _ddr([_own_row(lease="9999999-999")], _audited())
    report = validate_ddr(wb, _allow())
    assert any(f.rule == "foreign_unit_leakage" and "9999999-999" in f.expected
               for f in report.failures)


def test_catches_commentary_in_a_client_cell():
    wb = _ddr([_own_row(royalty="REVIEW REQUIRED — check p.8")], _audited())
    report = validate_ddr(wb, _allow())
    assert any(f.rule == "client_facing_commentary" for f in report.failures)


def test_catches_an_unsourced_derived_value():
    wb = _ddr([_own_row()], audit=[])       # no audit row for row 8
    report = validate_ddr(wb, _allow())
    assert any(f.rule == "audit_trace" for f in report.failures)


# --- clean workbook / reporting -------------------------------------------

def test_a_clean_ddr_is_ready():
    wb = _ddr([_own_row()], _audited())
    report = validate_ddr(wb, _allow())
    assert report.ready, console_summary(report)
    assert not report.failures


def test_findings_carry_sheet_cell_value_rule_and_expected():
    wb = _ddr([_own_row()], _audited())
    wb["Ownership Report"]["C815"] = "A"
    finding = next(f for f in validate_ddr(wb, _allow()).failures if f.cell == "C815")
    assert finding.sheet == "Ownership Report" and finding.value == "A"
    assert finding.rule and finding.expected and finding.severity == FAIL
    assert "C815" in finding.describe()


def test_report_goes_to_a_sidecar_and_never_into_the_deliverable(tmp_path):
    wb = _ddr([_own_row()], _audited())
    wb["Ownership Report"]["C815"] = "A"
    report = validate_ddr(wb, _allow())
    ddr = tmp_path / "MAXWELL_A_UNIT_DDR_20260716.xlsx"
    wb.save(ddr)
    before = set(openpyxl.load_workbook(ddr).sheetnames)

    sidecar = write_validation_sidecar(report, ddr)

    assert sidecar.name == "MAXWELL_A_UNIT_DDR_20260716_validation.txt"
    assert sidecar.parent == ddr.parent               # next to the DDR
    body = sidecar.read_text(encoding="utf-8")
    assert "C815" in body and "orphan_cell" in body
    # The deliverable is untouched: no tab added, nothing rewritten.
    assert set(openpyxl.load_workbook(ddr).sheetnames) == before
    assert "DD_Validation" not in before



def test_console_summary_itemizes_every_failure():
    wb = _ddr([_own_row(nri=None)], _audited())
    wb["Ownership Report"]["C815"] = "A"
    text = console_summary(validate_ddr(wb, _allow()))
    assert "NOT READY" in text and "cells checked" in text
    assert "C815" in text and "nri_sanity" in text


def test_allowlist_is_derived_from_xref_and_dpu():
    rows = [{"lease_no": "0190122-001", "contract_no": "K1400813",
             "contract_name": "DECL OF POOLED UNIT - MAXWELL UNIT A",
             "record_type": "UNIT AGREEMENT"},
            {"lease_no": "0190122-001", "contract_no": "K1400235",
             "contract_name": "DECL OF POOLED UNIT - WIESE UNIT",
             "record_type": "UNIT AGREEMENT"}]
    allow = build_allowlist("MAXWELL A UNIT", rows, ["0190122-001"])
    assert "K1400813" in allow.contracts and "K1400235" in allow.contracts
    assert "WIESE" in allow.foreign_unit_names       # another unit's DPU
    assert "MAXWELL" not in allow.foreign_unit_names  # never our own unit
    assert allow.foreign_units_in("Wiese Unit opinion") == {"WIESE"}


# --- the two rules that were wrong when first run against the real workbook ---

def test_approved_pending_stub_is_pending_not_a_failure():
    # The Agreements sheet stubs a contract known from the XREF whose PDF is not
    # in the file. That is the approved format and a recorded reason, inline.
    wb = _ddr([_own_row()], _audited(),
              extra={"Agreements": {"B23": "[PENDING - document not in file; found in XREF, order copy]"}})
    report = validate_ddr(wb, _allow())
    assert not [f for f in report.failures if f.rule == "client_facing_commentary"]
    assert any(f.rule == "pending_marker" and f.severity == PENDING for f in report.pending)


def test_real_triage_text_is_still_a_failure():
    wb = _ddr([_own_row()], _audited(),
              extra={"Agreements": {"B23": "TODO: ask Trevor about this one"}})
    report = validate_ddr(wb, _allow())
    assert any(f.rule == "client_facing_commentary" for f in report.failures)


def test_measure_words_before_unit_are_not_unit_names():
    # "a 160-acre unit", "the wellbore unit" — prose, not another unit.
    wb = _ddr([_own_row()], _audited(),
              extra={"Ownership - Wells": {"A9": "NOTE: Seller's WI in the wellbore unit; a 160 acre unit"}})
    report = validate_ddr(wb, _allow())
    assert not [f for f in report.failures if f.rule == "foreign_unit_leakage"]


def test_our_own_unit_named_in_prose_is_not_leakage():
    wb = _ddr([_own_row()], _audited(),
              extra={"Summary": {"B7": "Maxwell A Unit - 160 acres, Calhoun County School Land Survey"}})
    report = validate_ddr(wb, _allow())
    assert not [f for f in report.failures if f.rule == "foreign_unit_leakage"]


def test_a_lessor_surname_shared_with_another_unit_is_not_leakage():
    # Deriving "unit names" from contract titles yields every landowner surname
    # in the county; Maxwell's own parties (Kramer, Lynn, Parker) are among them.
    allow = _allow()
    allow.foreign_unit_names |= {"KRAMER", "LYNN", "PARKER"}
    wb = _ddr([_own_row()], _audited(),
              extra={"Lease Review": {"C3": "Lynn W. Cox", "C4": "Kramer Mineral Trust",
                                      "C5": "Marilyn J. Parker"}})
    report = validate_ddr(wb, allow)
    assert not [f for f in report.failures if f.rule == "foreign_unit_leakage"]


def test_another_units_name_phrase_is_still_caught():
    wb = _ddr([_own_row()], _audited(),
              extra={"PLM Title Review": {"A9": "Wiese Unit opinion, 50.73 acres"}})
    report = validate_ddr(wb, _allow())
    assert any(f.rule == "foreign_unit_leakage" and "WIESE" in f.expected.upper()
               for f in report.failures)


# --- the deliverable's tab set must equal the template's ---

def _template(tabs=("Summary", "Ownership Report", "Ownership - Wells", "Lease Review",
                    "Agreements", "Unit and Pooling Agreements", "Runsheet",
                    "PLM Title Review", "Disclaimer", "Ownership - 1H (No FO Option)",
                    "delete - A.E. Carroll 4H")):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for t in tabs:
        wb.create_sheet(t)
    return wb


def test_expected_set_drops_the_templates_scratch_tab_and_adds_the_audit_trail():
    expected = expected_sheet_set(_template())
    assert "delete - A.E. Carroll 4H" not in expected   # must never ship
    assert "DD_Audit_Trail" in expected                 # invariant 5: traceability
    assert "Ownership Report" in expected


def test_an_extra_tab_fails():
    wb = _ddr([_own_row()], _audited(), extra={"Scratch copy": {"A1": "x"}})
    expected = {"Ownership Report", "DD_Audit_Trail"}
    report = validate_ddr(wb, _allow(), expected_sheets=expected)
    assert any(f.rule == "sheet_set" and f.cell == "Scratch copy" for f in report.failures)
    assert not report.ready


def test_the_validators_own_tab_would_fail(tmp_path):
    # The reason the report is a sidecar: emitting DD_Validation into the
    # deliverable would make the workbook fail its own tab-set rule.
    wb = _ddr([_own_row()], _audited())
    wb.create_sheet("DD_Validation")
    report = validate_ddr(wb, _allow(), expected_sheets={"Ownership Report", "DD_Audit_Trail"})
    assert any(f.rule == "sheet_set" and f.cell == "DD_Validation" for f in report.failures)


def test_a_missing_template_tab_fails():
    wb = _ddr([_own_row()], _audited())
    expected = {"Ownership Report", "DD_Audit_Trail", "Disclaimer"}
    report = validate_ddr(wb, _allow(), expected_sheets=expected)
    assert any(f.rule == "sheet_set" and f.cell == "Disclaimer" and f.value is None
               for f in report.failures)


def test_the_scratch_tab_shipping_fails():
    wb = _ddr([_own_row()], _audited(), extra={"delete - A.E. Carroll 4H": {"A1": "sample"}})
    report = validate_ddr(wb, _allow(), expected_sheets={"Ownership Report", "DD_Audit_Trail"})
    scratch = [f for f in report.failures if f.rule == "sheet_set"]
    assert any("never ship" in f.expected for f in scratch)


def test_the_exact_expected_tab_set_passes():
    wb = _ddr([_own_row()], _audited())
    report = validate_ddr(wb, _allow(), expected_sheets={"Ownership Report", "DD_Audit_Trail"})
    assert not [f for f in report.failures if f.rule == "sheet_set"]
    assert report.ready


def test_tab_set_rule_is_skipped_when_no_template_is_supplied():
    wb = _ddr([_own_row()], _audited(), extra={"Whatever": {"A1": "x"}})
    report = validate_ddr(wb, _allow())          # expected_sheets=None
    assert not [f for f in report.failures if f.rule == "sheet_set"]


# --- PENDING claiming "not in file" while the document is ON DISK = FAIL ---
# The real defect: three Agreements blocks said "[PENDING - document not in
# file]" while all three contract packages sat in the unit's project folder.

def test_documents_on_disk_reads_identifiers_from_filenames(tmp_path):
    from src.dd.ddr_validator import documents_on_disk
    (tmp_path / "K1400049 (ASMT - JOE BOB SMITH-ASSIGNMENT).zip").write_bytes(b"x")
    sub = tmp_path / "NEW FILES"; sub.mkdir()
    (sub / "0190122-005 (HRABOVSKY).zip").write_bytes(b"x")
    docs = documents_on_disk(tmp_path)
    assert {"K1400049", "0190122-005"} <= docs


def test_pending_with_document_on_disk_fails():
    wb = _ddr([_own_row()], _audited(),
              extra={"Agreements": {"A21": "K1400049",
                                    "B23": "[PENDING - document not in file; awaiting contract PDF]"}})
    report = validate_ddr(wb, _allow(), documents_available={"K1400049"})
    hits = [f for f in report.failures if f.rule == "pending_document_on_disk"]
    assert hits and "K1400049" in hits[0].expected
    assert not report.ready


def test_pending_with_document_genuinely_absent_stays_pending():
    wb = _ddr([_own_row()], _audited(),
              extra={"Agreements": {"A21": "K9999999",
                                    "B23": "[PENDING - document not in file; awaiting contract PDF]"}})
    report = validate_ddr(wb, _allow(), documents_available={"K1400049"})
    assert not [f for f in report.failures if f.rule == "pending_document_on_disk"]
    assert any(f.rule == "pending_marker" for f in report.pending)


def test_identifier_inside_the_marker_text_is_also_checked():
    wb = _ddr([_own_row()], _audited(),
              extra={"Agreements": {"B5": "[PENDING - K1400347 not in file]"}})
    report = validate_ddr(wb, _allow(), documents_available={"K1400347"})
    assert any(f.rule == "pending_document_on_disk" for f in report.failures)


def test_rule_is_skipped_without_a_disk_inventory():
    wb = _ddr([_own_row()], _audited(),
              extra={"Agreements": {"A21": "K1400049", "B23": "[PENDING - not in file]"}})
    report = validate_ddr(wb, _allow())          # documents_available=None
    assert not [f for f in report.failures if f.rule == "pending_document_on_disk"]


def test_stated_nowhere_in_instrument_is_a_resolved_reason():
    from src.dd.dd_pending import PendingReason, PendingRegistry
    reg = PendingRegistry()
    item = reg.add("Agreements", "B27", "Tax Partnership",
                   PendingReason.STATED_NOWHERE_IN_INSTRUMENT,
                   "the recorded assignment has no tax-partnership article")
    assert not item.is_outstanding          # the blank IS the finished answer
    assert reg.outstanding == []


# --- source truth is part of READY: form alone is not enough ---

def _truth(mismatches=0):
    from src.dd.source_truth_check import TruthFinding, TruthReport, MISMATCH, CONFIRMED
    r = TruthReport()
    r.add(TruthFinding("Ownership Report", "K8/L8", "Record Book/Page", "Vol 402, Pg 50",
                       "Vol 402, Pg 50", CONFIRMED, source_file="DPU Exhibit A"))
    for i in range(mismatches):
        r.add(TruthFinding("Ownership Report", f"K{16+i}/L{16+i}", "Record Book/Page",
                           "Vol 475, Pg 39", "Vol 405, Pg 343", MISMATCH,
                           source_file="DPU Exhibit A"))
    return r


def test_structurally_clean_but_contradicting_its_source_is_not_ready():
    # The whole point: a cell can be perfectly formed and still false.
    wb = _ddr([_own_row()], _audited())
    report = validate_ddr(wb, _allow())
    assert report.ready                      # form alone: fine
    report.truth = _truth(mismatches=1)
    assert not report.ready                  # truth: contradicted -> blocked
    assert len(report.source_mismatches) == 1
    assert "source truth" in report.summary()


def test_ready_needs_zero_structural_fail_and_zero_mismatch():
    wb = _ddr([_own_row()], _audited())
    report = validate_ddr(wb, _allow())
    report.truth = _truth(mismatches=0)
    assert report.ready
    assert "READY" in report.summary()


def test_unverifiable_cells_do_not_block_ready():
    from src.dd.source_truth_check import TruthFinding, UNVERIFIABLE
    wb = _ddr([_own_row()], _audited())
    report = validate_ddr(wb, _allow())
    t = _truth(mismatches=0)
    t.add(TruthFinding("Lease Review", "E9", "lease date", "1/14/2010", None,
                       UNVERIFIABLE, detail="no lease PDF on disk"))
    report.truth = t
    assert report.ready                      # a known gap is not a defect
    assert len(report.truth.unverifiable) == 1


def test_console_summary_includes_the_truth_table():
    wb = _ddr([_own_row()], _audited())
    report = validate_ddr(wb, _allow())
    report.truth = _truth(mismatches=1)
    text = console_summary(report)
    assert "SOURCE TRUTH" in text and "MISMATCH" in text
