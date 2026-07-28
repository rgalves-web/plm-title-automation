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


def test_declared_sheet_exclusion_logs_DECLARED_not_FAIL():
    # Bowen: "Ownership - 1H (No FO Option)" deliberately deleted by the landman.
    from src.dd.ddr_validator import check_sheet_set
    wb = _ddr([_own_row()], _audited())
    expected = set(wb.sheetnames) | {"Ownership - 1H (No FO Option)"}
    declared = {"Ownership - 1H (No FO Option)":
                "excluída deliberadamente pelo landman 07/28 — análise No FO Option "
                "fora do escopo desta entrega"}
    findings = check_sheet_set(wb, expected, declared_exclusions=declared)
    decl = [f for f in findings if f.severity == "DECLARED"]
    assert len(decl) == 1 and "DECLARED EXCLUSION" in decl[0].expected
    assert not [f for f in findings if f.severity == FAIL]


def test_undeclared_missing_sheet_still_fails():
    from src.dd.ddr_validator import check_sheet_set
    wb = _ddr([_own_row()], _audited())
    expected = set(wb.sheetnames) | {"Ownership - 1H (No FO Option)"}
    findings = check_sheet_set(wb, expected, declared_exclusions={"Some Other Tab": "x"})
    assert [f for f in findings if f.severity == FAIL and f.rule == "sheet_set"]


def test_extra_tab_is_never_excusable_by_declaration():
    from src.dd.ddr_validator import check_sheet_set
    wb = _ddr([_own_row()], _audited())
    wb.create_sheet("Stray Copy")
    findings = check_sheet_set(wb, set(wb.sheetnames) - {"Stray Copy"},
                               declared_exclusions={"Stray Copy": "nice try"})
    assert [f for f in findings if f.severity == FAIL and f.cell == "Stray Copy"]


def test_common_english_words_before_unit_do_not_flag_but_real_names_do():
    # Bowen artifacts: "a DIFFERENT unit", "OUTSIDE unit boundary", "AFFECTS
    # unit". A real neighboring unit (SIEBOLD) must still flag — the stoplist
    # is safe only because no unit is plausibly NAMED a function word.
    allow = _allow()
    assert allow.foreign_units_in("leases feed a DIFFERENT Unit entirely") == set()
    assert allow.foreign_units_in("tract lies OUTSIDE Unit boundary") == set()
    assert allow.foreign_units_in("the amendment AFFECTS Unit acreage") == set()
    assert "SIEBOLD" in allow.foreign_units_in("covered by the SIEBOLD Unit opinion")


def test_pending_text_in_tract_gross_is_reported_not_a_crash():
    # Bowen: gross acres carried "Pending tract allocation (Brim legals … see
    # Original T-O 4/15/2008 request)" — a string. The gate must run and name
    # the row as PENDING, not die on float().
    wb = _ddr([_own_row(gross="Pending tract allocation (Brim legals: Brooks "
                              "A-35 / Stephenson A-682 area)")],
              _audited())
    report = validate_ddr(wb, _allow())          # must not raise
    pend = [f for f in report.findings
            if f.rule == "mi_per_tract_sum" and f.severity == PENDING]
    assert pend and "not numeric" in pend[0].expected
    assert not [f for f in report.failures if f.rule == "mi_per_tract_sum"]


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


# --- PLM submission checklist: item 7 (date), 8 (disclaimer), 10 (headers) ---

def _sheet_wb(cells: dict[str, dict[str, object]]):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, values in cells.items():
        ws = wb.create_sheet(name)
        for coord, value in values.items():
            ws[coord] = value
    return wb


def test_hardcoded_past_submission_date_fails():
    from datetime import date
    from src.dd.ddr_validator import check_submission_date
    wb = _sheet_wb({"PLM Title Review": {"A7": "Date:", "B7": "7/7/2026"}})
    hits = check_submission_date(wb, today=date(2026, 7, 16))
    assert hits and hits[0].severity == FAIL
    assert "in the past" in hits[0].expected and hits[0].cell == "B7"


def test_submission_date_token_is_pending_confirm_not_a_failure():
    from datetime import date
    from src.dd.ddr_validator import SUBMISSION_DATE_TOKEN, check_submission_date
    wb = _sheet_wb({"PLM Title Review": {"A7": "Date:", "B7": SUBMISSION_DATE_TOKEN}})
    hits = check_submission_date(wb, today=date(2026, 7, 16))
    assert hits and hits[0].severity == PENDING
    assert "confirm submission date" in hits[0].expected


def test_todays_submission_date_passes():
    from datetime import date
    from src.dd.ddr_validator import check_submission_date
    wb = _sheet_wb({"Summary": {"A9": "Date Submitted:", "B9": "7/16/2026"}})
    assert check_submission_date(wb, today=date(2026, 7, 16)) == []


def test_date_submitted_label_is_checked_too():
    from datetime import date
    from src.dd.ddr_validator import check_submission_date
    wb = _sheet_wb({"Summary": {"A9": "Date Submitted:", "B9": "7/7/2026"}})
    assert check_submission_date(wb, today=date(2026, 7, 16))[0].severity == FAIL


def test_disclaimer_stand_in_company_fails():
    from src.dd.ddr_validator import check_disclaimer_names_the_client
    wb = _sheet_wb({"Disclaimer": {"B6": "shall become the property of ABC, LLC and its subsidiaries."}})
    hits = check_disclaimer_names_the_client(wb, "BKV Corp.")
    assert hits and hits[0].rule == "disclaimer_names_the_client"
    assert "BKV Corp." in hits[0].expected


def test_disclaimer_naming_the_client_passes():
    from src.dd.ddr_validator import check_disclaimer_names_the_client
    wb = _sheet_wb({"Disclaimer": {"B6": "shall become the property of BKV Corp. and its subsidiaries."}})
    assert check_disclaimer_names_the_client(wb, "BKV Corp.") == []


def test_disclaimer_that_names_nobody_fails():
    from src.dd.ddr_validator import check_disclaimer_names_the_client
    wb = _sheet_wb({"Disclaimer": {"B6": "shall become the property of the undersigned."}})
    hits = check_disclaimer_names_the_client(wb, "BKV Corp.")
    assert hits and "never names the client" in hits[0].expected


def test_template_placeholder_in_a_header_fails():
    from src.dd.ddr_validator import check_headers_have_no_placeholder
    wb = _sheet_wb({"Ownership Report": {"A1": "636.13 acres in Reeves County"}})
    hits = check_headers_have_no_placeholder(wb)
    assert hits and hits[0].rule == "template_placeholder_in_header"


def test_a_real_unit_header_passes():
    from src.dd.ddr_validator import check_headers_have_no_placeholder
    wb = _sheet_wb({"Ownership Report": {
        "A1": "Verified Lease Ownership Interests\n\nMAXWELL A UNIT, MONTAGUE County, Texas"}})
    assert check_headers_have_no_placeholder(wb) == []


def test_placeholder_below_the_header_rows_is_not_this_rule():
    from src.dd.ddr_validator import check_headers_have_no_placeholder
    wb = _sheet_wb({"Ownership Report": {"A9": "Reeves"}})   # body, not header
    assert check_headers_have_no_placeholder(wb) == []


def test_header_identical_to_the_templates_legal_description_fails():
    # The real miss: "Ownership - 1H" shipped with the template's 704.04-acre
    # W.W. Boaton legal description verbatim. A token list never caught it.
    from src.dd.ddr_validator import check_headers_have_no_placeholder
    legal = ("Verified Lease Ownership Interests\n\nBeing 704.04 acres of land, more or "
             "less, out of the W.W. Boaton Survey, A-113")
    tpl = _sheet_wb({"Ownership - 1H (No FO Option)": {"A1": legal}})
    ddr = _sheet_wb({"Ownership - 1H (No FO Option)": {"A1": legal}})
    hits = check_headers_have_no_placeholder(ddr, tpl)
    assert hits and "never filled in" in hits[0].expected


def test_header_filled_with_this_units_legal_passes():
    from src.dd.ddr_validator import check_headers_have_no_placeholder
    tpl = _sheet_wb({"Ownership - 1H (No FO Option)": {
        "A1": "Verified Lease Ownership Interests\n\nBeing 704.04 acres out of the W.W. Boaton Survey, A-113"}})
    ddr = _sheet_wb({"Ownership - 1H (No FO Option)": {
        "A1": "Verified Lease Ownership Interests\n\n160 acres, Calhoun County School Land Survey, League 12, A-122"}})
    assert check_headers_have_no_placeholder(ddr, tpl) == []


def test_a_shared_non_legal_header_is_not_a_placeholder():
    # "Verified Lease Ownership Interests" matches the template by design.
    from src.dd.ddr_validator import check_headers_have_no_placeholder
    tpl = _sheet_wb({"Ownership Report": {"A1": "Verified Lease Ownership Interests"}})
    ddr = _sheet_wb({"Ownership Report": {"A1": "Verified Lease Ownership Interests"}})
    assert check_headers_have_no_placeholder(ddr, tpl) == []


def test_template_example_left_on_a_filled_row_fails():
    # The real defect: every Lease Review row got its real lease number, but the
    # pooling-clause column kept the template's example clause verbatim — all 30.
    from src.dd.ddr_validator import check_template_value_not_replaced
    clause = "Yes (Pooling units for oil up to 40 acres with 10% tolerance)"
    tpl = _sheet_wb({"Lease Review": {"A2": "L1", "O2": clause}})
    ddr = _sheet_wb({"Lease Review": {"A2": "0190122-001", "O2": clause}})
    hits = check_template_value_not_replaced(ddr, tpl)
    assert hits and hits[0].cell == "O2"
    assert "never filled" in hits[0].expected


def test_a_row_the_writer_never_touched_is_not_flagged():
    # Untouched template rows are the template's business, not a filled-row defect.
    from src.dd.ddr_validator import check_template_value_not_replaced
    clause = "Yes (Pooling units for oil up to 40 acres with 10% tolerance)"
    tpl = _sheet_wb({"Lease Review": {"A2": "L1", "O2": clause}})
    ddr = _sheet_wb({"Lease Review": {"A2": "L1", "O2": clause}})
    assert check_template_value_not_replaced(ddr, tpl) == []


def test_a_genuinely_filled_cell_passes():
    from src.dd.ddr_validator import check_template_value_not_replaced
    tpl = _sheet_wb({"Lease Review": {"A2": "L1", "O2": "Yes (Pooling units up to 40 acres)"}})
    ddr = _sheet_wb({"Lease Review": {"A2": "0190122-001",
                                       "O2": "Lessee may pool without Lessor consent, 640-acre gas units"}})
    assert check_template_value_not_replaced(ddr, tpl) == []


def test_short_shared_labels_are_not_flagged():
    # "Fee", "Yes", "N/A" legitimately coincide with the template.
    from src.dd.ddr_validator import check_template_value_not_replaced
    tpl = _sheet_wb({"Lease Review": {"A2": "L1", "D2": "Fee"}})
    ddr = _sheet_wb({"Lease Review": {"A2": "0190122-001", "D2": "Fee"}})
    assert check_template_value_not_replaced(ddr, tpl) == []


def test_col_O_pooling_clause_is_covered_specifically():
    # The defect that started this: every Lease Review row carried the
    # template's example pooling clause in col O.
    from src.dd.ddr_validator import check_template_value_not_replaced
    clause = "Yes (Pooling units for oil up to 40 acres (with 10% tolerance) and gas up to 640 acres)"
    tpl = _sheet_wb({"Lease Review": {"A2": "L1", "O2": clause, "A3": "L2", "O3": clause}})
    ddr = _sheet_wb({"Lease Review": {"A2": "0190122-001", "O2": clause,
                                       "A3": "0190122-005", "O3": clause}})
    hits = check_template_value_not_replaced(ddr, tpl)
    assert {f.cell for f in hits} == {"O2", "O3"}, "col O must be caught on every filled row"


def test_col_O_filled_from_the_lease_passes():
    from src.dd.ddr_validator import check_template_value_not_replaced
    clause = "Yes (Pooling units for oil up to 40 acres (with 10% tolerance) and gas up to 640 acres)"
    tpl = _sheet_wb({"Lease Review": {"A2": "L1", "O2": clause}})
    ddr = _sheet_wb({"Lease Review": {"A2": "0190122-001",
        "O2": "Lessee has right but not obligation to pool. Unit for oil well not to exceed 40 acres "
              "plus 10% tolerance (see LEASE.TIF p.1 for full clause)"}})
    assert check_template_value_not_replaced(ddr, tpl) == []


def test_col_O_blanked_pending_document_passes():
    # A blank with a recorded reason beats a false clause from another deal.
    from src.dd.ddr_validator import check_template_value_not_replaced
    clause = "Yes (Pooling units for oil up to 40 acres (with 10% tolerance) and gas up to 640 acres)"
    tpl = _sheet_wb({"Lease Review": {"A2": "L1", "O2": clause}})
    ddr = _sheet_wb({"Lease Review": {"A2": "0220335-001", "O2": None}})
    assert check_template_value_not_replaced(ddr, tpl) == []


# --- Vol/Page vs the DPU Exhibit A: the Flynt "Volume 37 vs 371" defect ---
# This shipped and was caught ONLY because an amber flag happened to sit on the
# cell. A dropped digit is invisible on a page of volume numbers; luck is not a
# control. Exhibit A decides it mechanically, so it FAILS.

_DPU_EXHIBIT_A = {
    "0190122-001": ("402", "50"),
    "0190122-006": ("371", "293"),      # Jon Robert Flynt
    "0220344-006": ("405", "343"),      # Marie Hulme
    "0220344-009": ("475", "39"),       # John A. Cox
    "0220344-024": (None, None),        # the DPU itself prints "Volume__, Page__"
}


def _own_recording(rows: list[tuple[str, object, object]]):
    """(lease, book, page) -> an Ownership Report with cols B/K/L."""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    ws = wb.create_sheet("Ownership Report")
    for i, (lease, book, page) in enumerate(rows):
        r = 8 + i
        ws.cell(r, 2).value = lease
        ws.cell(r, 11).value = book
        ws.cell(r, 12).value = page
    return wb


def test_flynt_volume_37_instead_of_371_fails():
    from src.dd.ddr_validator import check_recording_matches_dpu
    wb = _own_recording([("0190122-006", "37", "293")])   # digit dropped
    hits = check_recording_matches_dpu(wb, _DPU_EXHIBIT_A)
    assert len(hits) == 1
    assert hits[0].rule == "recording_matches_dpu"
    assert "Vol 371, Pg 293" in hits[0].expected      # what Exhibit A says
    assert "Vol 37, Pg 293" in hits[0].expected       # what the workbook says


def test_correct_flynt_recording_passes():
    from src.dd.ddr_validator import check_recording_matches_dpu
    wb = _own_recording([("0190122-006", "371", "293")])
    assert check_recording_matches_dpu(wb, _DPU_EXHIBIT_A) == []


def test_a_neighbouring_leases_recording_copied_in_fails():
    # Hulme's row carrying John A Cox's 475/39 — the same class of defect.
    from src.dd.ddr_validator import check_recording_matches_dpu
    wb = _own_recording([("0220344-006", "475", "39")])
    hits = check_recording_matches_dpu(wb, _DPU_EXHIBIT_A)
    assert hits and "Vol 405, Pg 343" in hits[0].expected


def test_transposed_page_fails():
    from src.dd.ddr_validator import check_recording_matches_dpu
    wb = _own_recording([("0190122-001", "402", "05")])   # 50 -> 05
    assert len(check_recording_matches_dpu(wb, _DPU_EXHIBIT_A)) == 1


def test_recording_blank_in_the_dpu_itself_is_not_a_failure():
    # The DPU prints "Volume__, Page__" for -024; nothing to contradict.
    from src.dd.ddr_validator import check_recording_matches_dpu
    wb = _own_recording([("0220344-024", "999", "1")])
    assert check_recording_matches_dpu(wb, _DPU_EXHIBIT_A) == []


def test_blank_recording_in_the_workbook_is_not_this_rules_business():
    # A blank carries its own pending reason; this rule judges wrong values.
    from src.dd.ddr_validator import check_recording_matches_dpu
    wb = _own_recording([("0190122-006", None, None)])
    assert check_recording_matches_dpu(wb, _DPU_EXHIBIT_A) == []


def test_lease_absent_from_exhibit_a_is_left_to_source_truth():
    from src.dd.ddr_validator import check_recording_matches_dpu
    wb = _own_recording([("9999999-999", "1", "2")])
    assert check_recording_matches_dpu(wb, _DPU_EXHIBIT_A) == []


def test_rule_is_skipped_without_a_dpu_map():
    from src.dd.ddr_validator import check_recording_matches_dpu
    wb = _own_recording([("0190122-006", "37", "293")])
    assert check_recording_matches_dpu(wb, None) == []


def test_a_wrong_recording_blocks_ready_end_to_end():
    wb = _ddr([_own_row()], _audited())
    ws = wb["Ownership Report"]
    ws.cell(8, 2).value = "0190122-006"
    ws.cell(8, 11).value = "37"
    ws.cell(8, 12).value = "293"
    report = validate_ddr(wb, _allow(), dpu_by_lease=_DPU_EXHIBIT_A)
    assert any(f.rule == "recording_matches_dpu" for f in report.failures)
    assert not report.ready


# --- no amber review fills survive into a deliverable ---

def test_amber_review_fill_fails():
    from openpyxl.styles import PatternFill
    from src.dd.ddr_validator import check_no_review_fills
    wb = _ddr([_own_row()], _audited())
    wb["Ownership Report"]["S8"].fill = PatternFill(
        fill_type="solid", start_color="FFEB9C", end_color="FFEB9C")
    hits = check_no_review_fills(wb)
    assert hits and hits[0].rule == "review_fill_present"
    assert "nobody has confirmed" in hits[0].expected


def test_a_workbook_with_no_flags_passes():
    from src.dd.ddr_validator import check_no_review_fills
    assert check_no_review_fills(_ddr([_own_row()], _audited())) == []


def test_other_fills_are_not_review_flags():
    from openpyxl.styles import PatternFill
    from src.dd.ddr_validator import check_no_review_fills
    wb = _ddr([_own_row()], _audited())
    wb["Ownership Report"]["S8"].fill = PatternFill(
        fill_type="solid", start_color="D9D9D9", end_color="D9D9D9")   # header grey
    assert check_no_review_fills(wb) == []


def test_a_review_fill_blocks_ready():
    from openpyxl.styles import PatternFill
    wb = _ddr([_own_row()], _audited())
    wb["Ownership Report"]["S8"].fill = PatternFill(
        fill_type="solid", start_color="FFEB9C", end_color="FFEB9C")
    assert not validate_ddr(wb, _allow()).ready


def test_an_unbuilt_allowlist_does_not_accuse_every_lease():
    # An empty allowlist means it never got built (missing XREF, unit not found)
    # — not that nothing belongs. Against the real Maxwell workbook this produced
    # 88 false failures across every sheet. It must stand down instead.
    from src.dd.ddr_validator import UnitAllowlist, check_foreign_unit
    empty = UnitAllowlist(unit_name="MAXWELL A UNIT", identity_tokens={"MAXWELL"})
    cells = [("B8", 8, 2, "0190122-001"), ("B9", 9, 2, "K1400813"), ("B10", 10, 2, "T0141486")]
    assert check_foreign_unit("Ownership Report", cells, empty) == []


def test_an_unbuilt_allowlist_still_catches_another_units_name():
    # Unit-name phrases need only our identity tokens, so they keep working.
    from src.dd.ddr_validator import UnitAllowlist, check_foreign_unit
    empty = UnitAllowlist(unit_name="MAXWELL A UNIT", identity_tokens={"MAXWELL"})
    cells = [("A9", 9, 1, "Wiese Unit opinion, 50.73 acres")]
    hits = check_foreign_unit("PLM Title Review", cells, empty)
    assert hits and "WIESE" in hits[0].expected.upper()


def test_a_populated_allowlist_still_catches_a_foreign_lease():
    from src.dd.ddr_validator import check_foreign_unit
    cells = [("B8", 8, 2, "9999999-999")]
    hits = check_foreign_unit("Ownership Report", cells, _allow())
    assert hits and "9999999-999" in hits[0].expected


# --- foreign-unit DATA is leakage; a foreign-unit TO cited as a SOURCE is not -
# Reviewer guidance: a neighbouring unit's TO is a valid source when it covers a
# shared leased tract. So "Wiese Unit T-O (T0140155)" in a note is legitimate,
# but a Wiese lease number or acreage in a client data cell is leakage.

def _allow_full():
    return UnitAllowlist(
        unit_name="MAXWELL A UNIT", identity_tokens={"MAXWELL"},
        leases={"0190122-005", "0190122-006"}, contracts={"K1400813"},
        title_opinions={"T0140253"}, foreign_unit_names={"WIESE", "ALAMO"})


def test_foreign_unit_TO_cited_as_a_source_in_a_note_passes():
    from src.dd.ddr_validator import check_foreign_unit
    cells = [("B13", 13, 2,
              "Wiese Unit T-O (File No. T0140155) is the source for leases "
              "0190122-005/-006 MI per Lease Analysis pp.61/63")]
    findings = check_foreign_unit("Summary", cells, _allow_full())
    assert findings == [], [f.describe() for f in findings]


def test_foreign_unit_opinion_cited_as_source_passes():
    from src.dd.ddr_validator import check_foreign_unit
    cells = [("A9", 9, 1, "0190122-005 MI confirmed against the Wiese Unit title opinion, shared tract")]
    assert check_foreign_unit("PLM Title Review", cells, _allow_full()) == []


def test_a_foreign_lease_number_as_DATA_is_still_leakage():
    from src.dd.ddr_validator import check_foreign_unit
    # A lease not in our set, in a plain data cell — leakage even if prose nearby.
    cells = [("B8", 8, 2, "9999999-999")]
    hits = check_foreign_unit("Ownership Report", cells, _allow_full())
    assert hits and "9999999-999" in hits[0].expected


def test_a_foreign_lease_number_is_leakage_even_beside_source_language():
    from src.dd.ddr_validator import check_foreign_unit
    # Citing a source does not launder a foreign lease IDENTIFIER into the data.
    cells = [("B8", 8, 2, "per Wiese T-O, lease 9999999-999 covers the tract")]
    hits = check_foreign_unit("Ownership Report", cells, _allow_full())
    assert any("9999999-999" in f.expected for f in hits)


def test_a_bare_foreign_unit_name_without_citation_is_leakage():
    from src.dd.ddr_validator import check_foreign_unit
    cells = [("A9", 9, 1, "Wiese Unit, 50.73 acres")]   # data, no citation language
    hits = check_foreign_unit("PLM Title Review", cells, _allow_full())
    assert any("WIESE" in f.expected.upper() for f in hits)


def test_a_foreign_TO_identifier_cited_as_source_is_allowed():
    from src.dd.ddr_validator import check_foreign_unit
    cells = [("B13", 13, 2, "source: T0140155 (Wiese Unit T-O) for 0190122-006, shared A-122 tract")]
    assert check_foreign_unit("Summary", cells, _allow_full()) == []
