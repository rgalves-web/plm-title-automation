"""Fill the DDR (Due Diligence Report) Excel template for one unit.

Reuses src/excel_writer.py's style-preserving machinery (row-template
capture/stamp, formula Translator, template-integrity report) rather than
reimplementing it. Three pieces of genuinely new logic not present in the MOR
writer: formula-aware flat tables (Ownership Report / Ownership - Wells),
card-block repetition with merged-cell replication (Agreements / Unit and
Pooling Agreements / PLM Title Review's per-TO section), and a hidden
DD_Audit_Trail provenance sheet.

Client-facing cells never contain MOR triage strings (REVIEW/REDLINE/
DUPLICATE/INCLUDE) or raw LLM commentary — low-confidence LLM-sourced values
get a visible yellow fill instead (mirrors MOR's review-yellow convention).
"""
from __future__ import annotations

from copy import copy
from dataclasses import dataclass, field
from datetime import date, datetime
from fractions import Fraction
from pathlib import Path
from shutil import copy2
from typing import Any

from openpyxl import load_workbook
from openpyxl.cell.cell import MergedCell
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.worksheet import Worksheet

from src.dd.manifest import UnitManifest
from src.dd.unit_aggregation import AggregationResult, ReconciliationResult
from src.excel_writer import (
    _apply_row_template,
    _build_template_integrity_report,
    _capture_row_template,
    _capture_workbook_snapshot,
)
from src.llm_extractor import HIGH_CONFIDENCE
from src.schemas import SourceDocument
from src.utils import safe_filename, timestamp, write_json

DELETE_TAB_NAME = "delete - A.E. Carroll 4H"
OWNERSHIP_1H_SHEET = "Ownership - 1H (No FO Option)"
REVIEW_FILL = PatternFill(fill_type="solid", start_color="FFEB9C", end_color="FFEB9C")

# Example/sample text baked into the client's blank DDR template (masked
# instrument numbers, the sample "*** Unit 3-11" Reeves County acquisition,
# the A.E. Carroll example unit). Any cell still containing one of these after
# all tabs are filled is leftover template noise, never real Project Emirates
# data — scrubbed wholesale before save so no placeholder reaches the client.
PLACEHOLDER_MARKERS = ("***", "Reeves", "636.13", "3-11", "A.E. Carroll", "Forest Oil")

AGREEMENTS_BLOCK_HEIGHT = 19
AGREEMENTS_TEMPLATE_BLOCK_COUNT = 2
UNIT_POOLING_BLOCK_HEIGHT = 8
UNIT_POOLING_TEMPLATE_BLOCK_COUNT = 1
TO_CARD_BLOCK_HEIGHT = 5
BLOCK_GAP_ROWS = 1

_AGREEMENT_RECORD_TYPES_FOR_AGREEMENTS_TAB = {"FARMOUT AGREEMENT", "ASSIGNMENT", "PURCHASE-SALE", "BILL OF SALE"}
_AGREEMENT_RECORD_TYPES_FOR_UNIT_POOLING_TAB = {
    "UNIT AGREEMENT",
    "DESIGNATION OF POOLED UNIT",
    "DECLARATION OF POOLED UNIT",
}


@dataclass
class AuditRow:
    sheet: str
    location: str
    source_type: str  # spreadsheet_row | to_pdf | formula | aggregation_computed
    source_reference: str
    confidence: float | None = None
    extracted_text: str | None = None


@dataclass
class DDReviewFlags:
    """Human-verification prompts surfaced on the Summary tab so the landman
    sees, in the deliverable itself, exactly what the automation could not
    close on its own."""
    potential_defects: list[str] = field(default_factory=list)
    curative_requirements: list[str] = field(default_factory=list)
    liens: list[str] = field(default_factory=list)
    section_notes: list[str] = field(default_factory=list)


@dataclass
class DDRWriteResult:
    output_path: Path
    integrity_report_path: Path
    audit_rows: list[AuditRow] = field(default_factory=list)


class DDRWriteContext:
    def __init__(self) -> None:
        self.audit_rows: list[AuditRow] = []
        self.inserted_ranges: list[dict[str, Any]] = []
        # Intentional deviations from the template, used to filter the
        # integrity report: cells the writer deliberately restyles/reformulates
        # (titles, totals, scrubbed placeholders) and whole row regions it owns
        # outright (data tables, card areas — stamped wholesale, so comparing
        # them against the template's example rows is meaningless).
        self.intentional_cells: set[tuple[str, str]] = set()
        self.rewritten_regions: list[tuple[str, int, int]] = []

    def record(self, sheet: str, location: str, source_type: str, source_reference: str,
               confidence: float | None = None, extracted_text: str | None = None) -> None:
        self.audit_rows.append(
            AuditRow(sheet, location, source_type, source_reference, confidence, extracted_text)
        )

    def own_cell(self, sheet: str, coordinate: str) -> None:
        self.intentional_cells.add((sheet, coordinate))

    def own_rows(self, sheet: str, start_row: int, end_row: int) -> None:
        self.rewritten_regions.append((sheet, start_row, end_row))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fill_ddr_template(
    template_path: str | Path,
    manifest: UnitManifest,
    output_dir: str | Path,
    aggregation: AggregationResult,
    reconciliation: ReconciliationResult,
    lease_review_rows: list[dict[str, Any]],
    runsheet_records: list[SourceDocument],
    runsheet_note: str,
    to_summaries: list[dict[str, Any]],
    review_flags: "DDReviewFlags | None" = None,
    runsheet_clean_note: str | None = None,
    pending_registry: Any | None = None,
) -> DDRWriteResult:
    template_path = Path(template_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{safe_filename(manifest.unit_name)}_DDR_{timestamp()}.xlsx"

    source_workbook = _load(template_path)
    source_snapshot = _capture_workbook_snapshot(source_workbook)
    # The "delete -" tab is removed from the output BY DESIGN — take it out of
    # the source snapshot so the integrity check compares the intended
    # client-facing surface instead of flagging the intentional removal.
    source_snapshot["sheet_names"] = [
        n for n in source_snapshot.get("sheet_names", []) if n != DELETE_TAB_NAME
    ]
    source_snapshot.get("sheets", {}).pop(DELETE_TAB_NAME, None)

    copy2(template_path, output_path)
    wb = _load(output_path)
    ctx = DDRWriteContext()

    _drop_delete_tab(wb)

    _fill_summary(wb, manifest, ctx, review_flags)
    _fill_ownership_report(wb, manifest, aggregation, lease_review_rows, ctx)
    _fill_ownership_wells(wb, manifest, aggregation, reconciliation, ctx)
    _fill_lease_review(wb, lease_review_rows, ctx)
    _fill_runsheet(wb, runsheet_records, runsheet_note, ctx, manifest=manifest, clean_note=runsheet_clean_note)
    _fill_plm_title_review(wb, manifest, to_summaries, ctx)
    _fill_agreements(wb, manifest, ctx)
    _fill_unit_and_pooling_agreements(wb, manifest, ctx)
    _apply_title_case(wb, ctx)
    _scrub_placeholders(wb, ctx)
    _write_audit_trail_sheet(wb, ctx)
    _write_pending_items_sheet(wb, pending_registry)

    wb.save(output_path)

    saved_workbook = _load(output_path)
    # DD_Audit_Trail (hidden provenance) and Pending Items (the blanks work list)
    # are added BY DESIGN — drop them from the comparison copy so
    # sheet_names_preserved checks the template's own tabs only. The saved file
    # on disk keeps both.
    for added_sheet in ("DD_Audit_Trail", "Pending Items"):
        if added_sheet in saved_workbook.sheetnames:
            del saved_workbook[added_sheet]
    integrity_report = _build_template_integrity_report(
        template_path=template_path,
        output_path=output_path,
        check=_passthrough_check(),
        source_snapshot=source_snapshot,
        saved_workbook=saved_workbook,
        inserted_range=ctx.inserted_ranges[0] if ctx.inserted_ranges else _empty_range(),
        additional_inserted_ranges=ctx.inserted_ranges[1:] if len(ctx.inserted_ranges) > 1 else [],
    )
    integrity_report = _apply_intentional_deviations(integrity_report, ctx)
    integrity_report_path = output_path.with_name(f"{output_path.stem}_integrity_report.json")
    write_json(integrity_report_path, integrity_report)

    return DDRWriteResult(
        output_path=output_path,
        integrity_report_path=integrity_report_path,
        audit_rows=ctx.audit_rows,
    )


def _load(path: str | Path):
    # Retry on PermissionError: on Windows, antivirus real-time scanning can hold
    # a brief lock on a freshly-copied .xlsx, blocking the immediate re-open. The
    # retry is output-neutral (it only re-attempts the same read).
    import time as _t

    last: Exception | None = None
    for attempt in range(6):
        try:
            return load_workbook(path, data_only=False)
        except PermissionError as exc:
            last = exc
            _t.sleep(0.3 * (attempt + 1))
    raise last


_DIFF_KEY_TO_CHECK = {
    "row_heights": "row_heights_outside_inserted_range_preserved",
    "formulas": "formulas_outside_inserted_range_preserved",
    "styles": "styles_outside_inserted_range_preserved",
    "wrap_text": "wrap_text_outside_inserted_range_preserved",
    "borders": "borders_outside_inserted_range_preserved",
    "number_formats": "number_formats_outside_inserted_range_preserved",
    "column_dimensions": "column_widths_preserved",
}


def _apply_intentional_deviations(report: dict[str, Any], ctx: DDRWriteContext) -> dict[str, Any]:
    """Drop integrity diffs the writer caused ON PURPOSE (rewritten data
    regions, retitled/refreshed cells, scrubbed placeholders) and recompute
    the pass/fail verdict. What survives this filter is genuinely unintended
    template damage."""
    import re as _re

    regions: dict[str, list[tuple[int, int]]] = {}
    for sheet, start_row, end_row in ctx.rewritten_regions:
        regions.setdefault(sheet, []).append((start_row, end_row))

    def _row_of(coordinate: str | None) -> int | None:
        if not coordinate:
            return None
        match = _re.search(r"(\d+)$", str(coordinate))
        return int(match.group(1)) if match else None

    def _is_intentional(diff: dict[str, Any]) -> bool:
        sheet = diff.get("sheet", "")
        coordinate = diff.get("cell")
        if coordinate and (sheet, coordinate) in ctx.intentional_cells:
            return True
        row = diff.get("row") if diff.get("row") is not None else _row_of(coordinate)
        if row is None:
            return False
        return any(start <= row <= end for start, end in regions.get(sheet, []))

    for diff_key, check_name in _DIFF_KEY_TO_CHECK.items():
        diffs = report.get("diffs", {}).get(diff_key) or []
        kept = [d for d in diffs if not _is_intentional(d)]
        report["diffs"][diff_key] = kept
        if check_name in report.get("checks", {}):
            report["checks"][check_name] = not kept
    report["passed"] = all(report["checks"].values())
    report["intentional_deviations_filtered"] = True
    return report


def _empty_range() -> dict[str, Any]:
    return {"sheet_name": "", "start_row": 0, "end_row": -1, "row_count": 0}


def _passthrough_check():
    from src.excel_writer import TemplateCheckResult

    return TemplateCheckResult(passed=True, sheet_name=None, header_row=None)


# ---------------------------------------------------------------------------
# Sheet removal
# ---------------------------------------------------------------------------

def _drop_delete_tab(wb) -> None:
    """Only the explicit "delete -" tab is removed. "Ownership - 1H (No FO
    Option)" is retained unconditionally — peer DDRs keep it regardless of
    farmout scenario, so dropping it made our deliverable diverge from the
    format reviewers expect (its example text is scrubbed like every tab's)."""
    if DELETE_TAB_NAME in wb.sheetnames:
        del wb[DELETE_TAB_NAME]


def _insert_rows_preserving_heights(ws, insert_at: int, amount: int) -> None:
    """ws.insert_rows shifts cell content but NOT row_dimensions, so template
    rows below the insertion silently lose their custom heights (they keep the
    height of whatever row number they used to be). Shift the stored heights
    down by `amount` alongside the content."""
    ws.insert_rows(insert_at, amount=amount)
    dims = ws.row_dimensions
    moved = {r: dims[r].height for r in list(dims) if r >= insert_at}
    for row_number in moved:
        dims[row_number].height = None
    for row_number, height in moved.items():
        if height is not None:
            dims[row_number + amount].height = height


# Client-facing text columns to normalize to Title Case (Collin item 4):
# (sheet, first_data_row, [columns]). Numbers/fractions are never touched.
_TITLE_CASE_TARGETS = (
    ("Ownership Report", 8, (5, 6, 15)),   # WI Owner? no — lessor(5), lessee(6), legal(15)
    ("Lease Review", 2, (3, 4, 7)),        # lessor(3), lessee(4), legal desc(7)
)


def _apply_title_case(wb, ctx: "DDRWriteContext | None" = None) -> None:
    """Config-driven ALL-CAPS -> Title Case pass over the client-facing name /
    legal columns of the Ownership Report and Lease Review tabs. Idempotent and
    exception-aware (LLC, Jr., A-122...) via src.dd.title_case."""
    from src.dd.title_case import to_title_case

    for sheet_name, first_row, cols in _TITLE_CASE_TARGETS:
        if sheet_name not in wb.sheetnames:
            continue
        ws = wb[sheet_name]
        for row_number in range(first_row, ws.max_row + 1):
            for col in cols:
                cell = ws.cell(row_number, col)
                if isinstance(cell, MergedCell) or not isinstance(cell.value, str):
                    continue
                new_value = to_title_case(cell.value)
                if new_value != cell.value:
                    cell.value = new_value
                    if ctx is not None:
                        ctx.own_cell(sheet_name, cell.coordinate)


def _scrub_placeholders(wb, ctx: "DDRWriteContext | None" = None) -> int:
    """Clear every cell still containing template placeholder text after all
    tabs are filled. Runs on all sheets; returns the number of cells cleared.
    Each cleared cell is registered as an intentional deviation so the
    integrity report does not count the scrub as template damage."""
    cleared = 0
    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        for row in ws.iter_rows():
            for cell in row:
                if isinstance(cell, MergedCell):
                    continue
                value = cell.value
                if isinstance(value, str) and any(marker in value for marker in PLACEHOLDER_MARKERS):
                    cell.value = None
                    cleared += 1
                    if ctx is not None:
                        ctx.own_cell(sheet_name, cell.coordinate)
    return cleared


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def _summary_flag_text(items: list[str]) -> str:
    """Render review flags as one bulleted block for a Summary cell, or the
    explicit "None identified" when there is nothing to flag — an affirmative
    statement the reviewer can rely on, not a placeholder dash."""
    if not items:
        return "None identified"
    return "\n".join(f"- {item}" for item in items)


def _fill_summary(
    wb,
    manifest: UnitManifest,
    ctx: DDRWriteContext,
    review_flags: "DDReviewFlags | None" = None,
) -> None:
    if "Summary" not in wb.sheetnames:
        return
    ws = wb["Summary"]
    values = {
        2: manifest.client_name or manifest.seller_name or "",
        3: manifest.acquisition_name or manifest.unit_name,
        4: manifest.operator or "",
        5: manifest.state,
        6: manifest.county or "",
        # DSU STR / PLM Landman / Date Submitted — None clears the template's
        # own example text when the manifest carries no value for them.
        7: manifest.dsu_description,
        8: manifest.landman_name,
        9: manifest.date_submitted,
    }
    for row_number, value in values.items():
        ws.cell(row_number, 2).value = value
        if value is not None:
            ctx.record("Summary", f"B{row_number}", "spreadsheet_row", "manifest")

    # Rows 10-13 are the review narrative: Potential Defect(s), Outstanding
    # Curative Requirements, Liens and Encumbrances, Section Notes. Populate
    # them with the automation's verification flags so the landman sees exactly
    # what to check by hand; fall back to the template's '--' when empty.
    flags = review_flags or DDReviewFlags()
    ws.cell(10, 2).value = _summary_flag_text(flags.potential_defects)
    ws.cell(11, 2).value = _summary_flag_text(flags.curative_requirements)
    ws.cell(12, 2).value = _summary_flag_text(flags.liens)
    ws.cell(13, 2).value = _summary_flag_text(flags.section_notes)
    for row_number in (10, 11, 12, 13):
        ws.cell(row_number, 2).alignment = Alignment(wrap_text=True, vertical="top")
        ctx.record("Summary", f"B{row_number}", "review_flag", "dd_pipeline")
    for row_number in range(2, 14):
        ctx.own_cell("Summary", f"B{row_number}")


# ---------------------------------------------------------------------------
# Ownership Report (formula-aware flat table)
# ---------------------------------------------------------------------------

def _fraction_formula_or_value(frac: Fraction) -> Any:
    """Write a fraction as an '=N/D' formula when reduced terms are small,
    matching the template's own convention (e.g. '=7/1280'); otherwise as a
    decimal value."""
    if frac.denominator <= 100000:
        return f"={frac.numerator}/{frac.denominator}"
    return float(frac)


def _fill_ownership_report(
    wb,
    manifest: UnitManifest,
    aggregation: AggregationResult,
    lease_review_rows: list[dict[str, Any]],
    ctx: DDRWriteContext,
) -> None:
    if "Ownership Report" not in wb.sheetnames:
        return
    ws = wb["Ownership Report"]

    legal = manifest.county and f"{manifest.unit_name}, {manifest.county} County, {manifest.state}" or manifest.unit_name
    ws.cell(1, 1).value = f"Verified Lease Ownership Interests\n\n{legal}"
    ws.cell(3, 1).value = f"Unit Verified Totals ({manifest.unit_name})"
    ws.cell(5, 1).value = float(aggregation.unit_gross_acres)

    data_start = 8
    template_row_count = 17  # rows 8-24 in the template example
    n = len(lease_review_rows)

    row_template = _capture_row_template(ws, data_start, ws.max_column)
    if n > template_row_count:
        _insert_rows_preserving_heights(ws, data_start + template_row_count, n - template_row_count)
    elif n < template_row_count:
        if n < 0:
            n = 0

    last_row = data_start + max(n, 0) - 1 if n else data_start - 1
    ws.cell(5, 2).value = f"=SUM(U{data_start}:U{max(last_row, data_start)})"
    ws.cell(5, 3).value = f"=SUM(X{data_start}:X{max(last_row, data_start)})"
    ws.cell(5, 4).value = "=B5/A5"
    ws.cell(5, 5).value = "=C5/A5"
    ctx.record("Ownership Report", "B5:E5", "formula", "aggregation_computed (SUM over detail rows)")

    for offset, row in enumerate(lease_review_rows):
        row_number = data_start + offset
        _apply_row_template(ws, row_number, row_template)
        ws.cell(row_number, 1).value = row.get("unit_tract_no", 1)
        ws.cell(row_number, 2).value = row.get("lease_no")
        ws.cell(row_number, 3).value = "WI"
        ws.cell(row_number, 4).value = manifest.seller_name
        ws.cell(row_number, 5).value = row.get("lessor")
        ws.cell(row_number, 6).value = row.get("lessee")
        ws.cell(row_number, 7).value = float(row["royalty"]) if row.get("royalty") is not None else None
        # Record Book / Page — the recording reference the unit's Declaration of
        # Pooled Unit (and its Amendment) prints for this lease in Exhibit "A".
        # Written as TEXT, matching the approved baseline: a volume/page is a
        # reference, not a quantity, and the baseline stores it as text.
        ws.cell(row_number, 11).value = row.get("record_book")
        ws.cell(row_number, 12).value = row.get("record_page")
        ws.cell(row_number, 14).value = manifest.county
        ws.cell(row_number, 15).value = row.get("legal_description")
        ws.cell(row_number, 18).value = float(row["tract_gross_acres"]) if row.get("tract_gross_acres") is not None else None
        ws.cell(row_number, 19).value = _fraction_formula_or_value(row["mi_value"]) if row.get("mi_value") is not None else None
        ws.cell(row_number, 20).value = _fraction_formula_or_value(row["wi_value"]) if row.get("wi_value") is not None else None
        ws.cell(row_number, 21).value = f"=R{row_number}*S{row_number}*T{row_number}"
        ws.cell(row_number, 22).value = f"=1-G{row_number}-W{row_number}"
        ws.cell(row_number, 23).value = float(row.get("orri_burdens", 0))
        ws.cell(row_number, 24).value = f"=U{row_number}*V{row_number}"

        source = row.get("source_to_file_number")
        ctx.record(
            "Ownership Report", f"row {row_number}",
            "to_pdf" if source else "spreadsheet_row",
            source or "Lease to Well XREF",
            confidence=row.get("confidence"),
        )
        if row.get("record_book_source"):
            ctx.record("Ownership Report", f"K{row_number}:L{row_number}", "dpu_exhibit_a",
                       row["record_book_source"], confidence=1.0,
                       extracted_text=f"Vol {row.get('record_book')}, Pg {row.get('record_page')}")
        if row.get("wi_source"):
            ctx.record("Ownership Report", f"T{row_number}", "to_pdf", row["wi_source"],
                       confidence=1.0)

    for row_number in range(data_start + n, data_start + template_row_count):
        for col in range(1, ws.max_column + 1):
            ws.cell(row_number, col).value = None

    for coordinate in ("A1", "A3", "A5", "B5", "C5", "D5", "E5"):
        ctx.own_cell("Ownership Report", coordinate)
    ctx.own_rows("Ownership Report", data_start, data_start + max(n, template_row_count) - 1)

    ctx.inserted_ranges.append(
        {"sheet_name": "Ownership Report", "start_row": data_start, "row_count": max(n - template_row_count, 0)}
    )


# ---------------------------------------------------------------------------
# Ownership - Wells (PSA vs Verified + Delta formulas)
# ---------------------------------------------------------------------------

def _fill_ownership_wells(
    wb,
    manifest: UnitManifest,
    aggregation: AggregationResult,
    reconciliation: ReconciliationResult,
    ctx: DDRWriteContext,
) -> None:
    if "Ownership - Wells" not in wb.sheetnames:
        return
    ws = wb["Ownership - Wells"]

    legal = manifest.county and f"{manifest.unit_name}, {manifest.county} County, {manifest.state}" or manifest.unit_name
    ws.cell(1, 1).value = f"Verified Well Ownership Interests\n\n{legal}"

    # The computed aggregate is a LEASEHOLD interest; the PSA/Well List figure
    # is a WELLBORE interest. When these bases differ (reconciliation N/A) the
    # "Verified" columns hold the leasehold figure and NO delta is written —
    # subtracting a wellbore PSA from a leasehold computation would imply a
    # defect that does not exist. Relabel the verified headers so the leasehold
    # basis is explicit in the deliverable itself.
    basis_differs = reconciliation.wi_status == "N/A" or reconciliation.nri_status == "N/A"
    if basis_differs:
        ws.cell(2, 15).value = "Seller Leasehold WI (Computed from TO)"
        ws.cell(2, 17).value = "Seller Leasehold NRI (Computed from TO)"
        ws.cell(2, 16).value = "WI Delta (N/A - basis differs)"
        ws.cell(2, 18).value = "NRI Delta (N/A - basis differs)"
        for coordinate in ("O2", "P2", "Q2", "R2"):
            ctx.own_cell("Ownership - Wells", coordinate)

    data_start = 3
    wells = manifest.wells
    template_row_count = 1
    if len(wells) > template_row_count:
        row_template = _capture_row_template(ws, data_start, ws.max_column)
        _insert_rows_preserving_heights(ws, data_start + template_row_count, len(wells) - template_row_count)
        for offset in range(template_row_count, len(wells)):
            _apply_row_template(ws, data_start + offset, row_template)

    for offset, well in enumerate(wells):
        row_number = data_start + offset
        ws.cell(row_number, 1).value = well.well_api
        ws.cell(row_number, 2).value = well.well_name
        ws.cell(row_number, 3).value = well.well_operator
        ws.cell(row_number, 5).value = well.well_prod_status
        ws.cell(row_number, 13).value = float(reconciliation.represented_wi)
        ws.cell(row_number, 14).value = float(reconciliation.represented_nri)
        ws.cell(row_number, 15).value = float(reconciliation.computed_wi)
        ws.cell(row_number, 17).value = float(reconciliation.computed_nri)
        if basis_differs:
            # No delta between different interest bases.
            ws.cell(row_number, 16).value = "N/A"
            ws.cell(row_number, 18).value = "N/A"
        else:
            ws.cell(row_number, 16).value = f"=M{row_number}-O{row_number}"
            ws.cell(row_number, 18).value = f"=N{row_number}-Q{row_number}"

        _flagged_statuses = ("WARNING", "NOT_COMPUTED")
        fill = (
            REVIEW_FILL
            if reconciliation.wi_status in _flagged_statuses or reconciliation.nri_status in _flagged_statuses
            else None
        )
        if fill:
            for col in (15, 16, 17, 18):
                ws.cell(row_number, col).fill = fill

        ctx.record(
            "Ownership - Wells", f"row {row_number}", "aggregation_computed",
            "unit_aggregation.run_dd_aggregation", confidence=None,
        )

    # The blank template ships with several sample well rows (masked API
    # numbers like "42-***-*****"). template_row_count assumes a single sample
    # row, so when the unit has fewer real wells than the template has samples,
    # the extra masked rows survive and read as real data. Clear every leftover
    # sample row below the ones we just filled. Stops at the first row with an
    # empty Well Name cell (column 2) — the trailing NOTE row has text in
    # column 1 but not column 2, so it is preserved.
    from openpyxl.cell.cell import MergedCell

    row_number = data_start + len(wells)
    while ws.cell(row_number, 2).value is not None:
        for col in range(1, ws.max_column + 1):
            cell = ws.cell(row_number, col)
            if not isinstance(cell, MergedCell):
                cell.value = None
        row_number += 1

    ctx.own_cell("Ownership - Wells", "A1")
    ctx.own_rows("Ownership - Wells", data_start, max(row_number - 1, data_start + len(wells) - 1, data_start))

    ctx.inserted_ranges.append(
        {"sheet_name": "Ownership - Wells", "start_row": data_start,
         "row_count": max(len(wells) - template_row_count, 0)}
    )


# ---------------------------------------------------------------------------
# Lease Review (flat table)
# ---------------------------------------------------------------------------

def _fill_lease_review(wb, lease_review_rows: list[dict[str, Any]], ctx: DDRWriteContext) -> None:
    if "Lease Review" not in wb.sheetnames:
        return
    ws = wb["Lease Review"]

    data_start = 2
    template_row_count = 18
    n = len(lease_review_rows)
    row_template = _capture_row_template(ws, data_start, ws.max_column)
    if n > template_row_count:
        _insert_rows_preserving_heights(ws, data_start + template_row_count, n - template_row_count)

    for offset, row in enumerate(lease_review_rows):
        row_number = data_start + offset
        _apply_row_template(ws, row_number, row_template)
        ws.cell(row_number, 1).value = row.get("lease_no")
        ws.cell(row_number, 2).value = row.get("lease_type", "Fee")
        ws.cell(row_number, 3).value = row.get("lessor")
        ws.cell(row_number, 4).value = row.get("lessee")
        ws.cell(row_number, 5).value = row.get("effective_date")
        ws.cell(row_number, 6).value = row.get("recording_info")
        ws.cell(row_number, 7).value = row.get("legal_description")
        ws.cell(row_number, 8).value = float(row["tract_gross_acres"]) if row.get("tract_gross_acres") is not None else None
        ws.cell(row_number, 9).value = row.get("primary_term")
        ws.cell(row_number, 10).value = row.get("royalty_text")
        ws.cell(row_number, 11).value = row.get("shut_in_royalty")
        ws.cell(row_number, 12).value = row.get("depth_limitations")
        ws.cell(row_number, 13).value = row.get("horizontal_pugh")
        ws.cell(row_number, 14).value = row.get("vertical_pugh")

        confidence = row.get("confidence")
        if confidence is not None and confidence < HIGH_CONFIDENCE:
            for col in range(1, 15):
                ws.cell(row_number, col).fill = REVIEW_FILL

        ctx.record(
            "Lease Review", f"row {row_number}",
            "to_pdf" if row.get("source_to_file_number") else "spreadsheet_row",
            row.get("source_to_file_number") or "Lease to Well XREF",
            confidence=confidence,
        )

    for row_number in range(data_start + n, data_start + template_row_count):
        for col in range(1, ws.max_column + 1):
            ws.cell(row_number, col).value = None

    ctx.own_rows("Lease Review", data_start, data_start + max(n, template_row_count) - 1)

    ctx.inserted_ranges.append(
        {"sheet_name": "Lease Review", "start_row": data_start, "row_count": max(n - template_row_count, 0)}
    )


# ---------------------------------------------------------------------------
# Runsheet (supplemental scope only)
# ---------------------------------------------------------------------------

def _fill_runsheet(
    wb,
    records: list[SourceDocument],
    note: str,
    ctx: DDRWriteContext,
    manifest: UnitManifest | None = None,
    clean_note: str | None = None,
) -> None:
    if "Runsheet" not in wb.sheetnames:
        return
    ws = wb["Runsheet"]

    # The A1 title cell bakes in a sample legal description on its own lines
    # ("Supplemental Title Runsheet\n\n636.13 acres ... Reeves County, Texas").
    # Rebuild it with this unit's descriptor so a wrong county never surfaces.
    if manifest is not None:
        legal = (
            f"{manifest.unit_name}, {manifest.county} County, {manifest.state}"
            if manifest.county
            else manifest.unit_name
        )
        ws.cell(1, 1).value = f"Supplemental Title Runsheet\n\n{legal}"

    ws.cell(3, 1).value = note

    data_start = 4
    template_row_count = 2
    n = len(records)
    row_template = _capture_row_template(ws, data_start, ws.max_column)
    if n > template_row_count:
        _insert_rows_preserving_heights(ws, data_start + template_row_count, n - template_row_count)

    for offset, record in enumerate(records):
        row_number = data_start + offset
        _apply_row_template(ws, row_number, row_template)
        ws.cell(row_number, 1).value = offset + 1
        ws.cell(row_number, 2).value = record.document_type
        ws.cell(row_number, 3).value = record.instrument_number
        ws.cell(row_number, 4).value = record.effective_date
        ws.cell(row_number, 5).value = record.instrument_date
        ws.cell(row_number, 6).value = record.recording_date
        ws.cell(row_number, 7).value = record.grantor
        ws.cell(row_number, 8).value = record.grantee
        for col in range(4, 7):
            ws.cell(row_number, col).number_format = "MM/DD/YYYY"

        ctx.record(
            "Runsheet", f"row {row_number}", "spreadsheet_row",
            record.source_document_id,
        )

    # Clear every leftover template sample row below the real records (the
    # template ships with more than template_row_count masked samples). Stops
    # at the first row whose INSTRUMENT cell (col 2) is empty.
    from openpyxl.cell.cell import MergedCell

    row_number = data_start + n
    while ws.cell(row_number, 2).value is not None:
        for col in range(1, ws.max_column + 1):
            cell = ws.cell(row_number, col)
            if not isinstance(cell, MergedCell):
                cell.value = None
        row_number += 1

    # A clean supplemental search is a finding, not an empty table: when no
    # instruments survived the scope filter, record the explanatory row the
    # landman would otherwise type by hand ("No instruments of record...").
    # Written after the sample-row sweep so it cannot be cleared as leftover.
    if n == 0 and clean_note:
        ws.cell(data_start, 1).value = "-"
        ws.cell(data_start, 2).value = clean_note
        ws.cell(data_start, 2).alignment = Alignment(wrap_text=True, vertical="top")
        ctx.record("Runsheet", f"row {data_start}", "aggregation_computed", "supplemental search - clean result")

    ctx.own_cell("Runsheet", "A1")
    ctx.own_cell("Runsheet", "A3")
    ctx.own_rows("Runsheet", data_start, max(row_number - 1, data_start + max(n, template_row_count) - 1))

    ctx.inserted_ranges.append(
        {"sheet_name": "Runsheet", "start_row": data_start, "row_count": max(n - template_row_count, 0)}
    )


# ---------------------------------------------------------------------------
# PLM Title Review (top block + repeating per-TO card)
# ---------------------------------------------------------------------------

def _certification_date_range(to_summaries: list[dict[str, Any]]) -> str:
    """Chronological min-max of the CONTROLLING opinions' certification dates
    (superseded originals don't define the review window), formatted M/D/YYYY.
    Raw certification strings sort wrong lexically ("December 11, 2012" <
    "May 2, 2008"), so parse first; unparseable values fall back to their raw
    text. When no summary carries the controlling flag, all are considered."""
    from src.pdf_reader import _parse_extracted_date

    controlling = [s for s in to_summaries if s.get("controlling")]
    considered = controlling or to_summaries

    parsed: list[date] = []
    raw_fallbacks: list[str] = []
    for summary in considered:
        raw = summary.get("certification_date")
        if not raw:
            continue
        value = _parse_extracted_date(str(raw))
        if value:
            parsed.append(value)
        else:
            raw_fallbacks.append(str(raw))

    if parsed:
        first, last = min(parsed), max(parsed)
        fmt = lambda d: f"{d.month}/{d.day}/{d.year}"
        return fmt(first) if first == last else f"{fmt(first)} - {fmt(last)}"
    if raw_fallbacks:
        return " - ".join(raw_fallbacks)
    return "TBD"


def _fill_plm_title_review(
    wb,
    manifest: UnitManifest,
    to_summaries: list[dict[str, Any]],
    ctx: DDRWriteContext,
) -> None:
    if "PLM Title Review" not in wb.sheetnames:
        return
    ws = wb["PLM Title Review"]

    ws.cell(2, 2).value = _certification_date_range(to_summaries)
    ws.cell(3, 2).value = manifest.unit_name
    ws.cell(4, 2).value = (
        f"Supplemental confirmatory title review limited to the leasehold interests of {manifest.seller_name}"
        if manifest.seller_name else None
    )
    ws.cell(5, 2).value = "Surface interests and interests outside of the leasehold interest of the Seller"
    ws.cell(6, 2).value = manifest.landman_name
    ws.cell(7, 2).value = manifest.date_submitted
    ctx.record("PLM Title Review", "B2:B7", "aggregation_computed", "controlling certification date range")

    card_start = 9
    template_block_count = 1
    n = len(to_summaries)
    if n == 0:
        for row_number in range(card_start, card_start + TO_CARD_BLOCK_HEIGHT):
            for col in (1, 2):
                cell = ws.cell(row_number, col)
                if not isinstance(cell, MergedCell):
                    cell.value = None
        return

    row_template = [
        _capture_row_template(ws, card_start + i, ws.max_column) for i in range(TO_CARD_BLOCK_HEIGHT)
    ]
    if n > template_block_count:
        extra_blocks = n - template_block_count
        insert_at = card_start + TO_CARD_BLOCK_HEIGHT
        _insert_rows_preserving_heights(ws, insert_at, extra_blocks * (TO_CARD_BLOCK_HEIGHT + BLOCK_GAP_ROWS))
        # Block b's content starts after its own leading gap row, not at insert_at.
        for b in range(extra_blocks):
            block_start = insert_at + BLOCK_GAP_ROWS + b * (TO_CARD_BLOCK_HEIGHT + BLOCK_GAP_ROWS)
            for i in range(TO_CARD_BLOCK_HEIGHT):
                _apply_row_template(ws, block_start + i, row_template[i])

    for offset, summary in enumerate(to_summaries):
        block_start = card_start + offset * (TO_CARD_BLOCK_HEIGHT + BLOCK_GAP_ROWS)
        ws.cell(block_start, 1).value = "Title Opinion Summary"
        ws.cell(block_start + 1, 2).value = summary.get("type_description") or summary.get("file_number")
        ws.cell(block_start + 2, 2).value = summary.get("certification_date")
        ws.cell(block_start + 3, 2).value = summary.get("legal_description")
        ws.cell(block_start + 4, 2).value = summary.get("requirements") or "-"

        confidence = summary.get("confidence")
        if confidence is not None and confidence < HIGH_CONFIDENCE:
            for i in range(TO_CARD_BLOCK_HEIGHT):
                ws.cell(block_start + i, 2).fill = REVIEW_FILL

        ctx.record(
            "PLM Title Review", f"block starting row {block_start}", "to_pdf",
            summary.get("file_number", ""), confidence=confidence,
        )

    for row_number in range(2, 8):
        ctx.own_cell("PLM Title Review", f"B{row_number}")
    ctx.own_rows(
        "PLM Title Review",
        card_start,
        card_start + max(n, 1) * (TO_CARD_BLOCK_HEIGHT + BLOCK_GAP_ROWS),
    )

    ctx.inserted_ranges.append(
        {
            "sheet_name": "PLM Title Review",
            "start_row": card_start + TO_CARD_BLOCK_HEIGHT,
            "row_count": max(n - template_block_count, 0) * (TO_CARD_BLOCK_HEIGHT + BLOCK_GAP_ROWS),
        }
    )


# ---------------------------------------------------------------------------
# Agreements / Unit and Pooling Agreements (card blocks)
# ---------------------------------------------------------------------------

def _write_contract_card_block(
    ws: Worksheet,
    block_start: int,
    block_height: int,
    entry: dict[str, Any],
) -> None:
    """Card block for the 'Agreements' tab (JOA / Farmout / Assignment cards).

    Layout (rows relative to block_start):
      +0  col A: record_type title ("JOA", "ASSIGNMENT" etc.) — VARIABLE
      +1  col A: file_number — VARIABLE
      +2  col A: "Operator:"  col B: lessee
      +3  col A: "Counterparty:"  col B: lessor
      +4…: col B = None (clear template sample values)
    """
    ws.cell(block_start, 1).value = entry.get("record_type")
    ws.cell(block_start + 1, 1).value = entry.get("file_number")
    ws.cell(block_start + 2, 1).value = "Operator:"
    ws.cell(block_start + 2, 2).value = entry.get("lessee")
    ws.cell(block_start + 3, 1).value = "Counterparty:"
    ws.cell(block_start + 3, 2).value = entry.get("lessor")
    for row_number in range(block_start + 4, block_start + block_height):
        ws.cell(row_number, 2).value = None


def _write_unit_pooling_card_block(
    ws: Worksheet,
    block_start: int,
    block_height: int,
    entry: dict[str, Any],
) -> None:
    """Card block for the 'Unit and Pooling Agreements' tab (DPU / Unit Agreement cards).

    The template's col A from row +2 onward has STATIC labels pre-printed
    ("Type:", "Recording Information:", "Effective Date:", "Unit Description:",
    "Formations:", "Notes:") — these must NOT be overwritten. Only col B is
    written for those rows.

    Layout:
      +0  col A: static "Unit/Pooling Agreement" header — NOT overwritten
      +1  col A: file_number / contract name — VARIABLE
      +2  col B only: record_type ("Designation of Pooled Unit" etc.)
      +3  col B only: recording_info
      +4  col B only: effective_date
      +5  col B only: unit_description
      +6  col B only: formations
      +7  col B only: notes
    """
    ws.cell(block_start + 1, 1).value = entry.get("file_number") or entry.get("record_type")

    col_b_values = [
        entry.get("record_type"),
        entry.get("recording_info"),
        entry.get("effective_date"),
        entry.get("unit_description") or entry.get("legal_description"),
        entry.get("formations"),
        entry.get("notes"),
    ]
    for offset, value in enumerate(col_b_values, start=2):
        if block_start + offset <= block_start + block_height - 1:
            cell = ws.cell(block_start + offset, 2)
            if not isinstance(cell, MergedCell):
                cell.value = value


def _fill_card_sheet(
    wb,
    sheet_name: str,
    block_height: int,
    template_block_count: int,
    entries: list[dict[str, Any]],
    ctx: DDRWriteContext,
    card_writer=None,
) -> None:
    if sheet_name not in wb.sheetnames:
        return
    ws = wb[sheet_name]
    n = len(entries)
    gap = BLOCK_GAP_ROWS
    total_template_rows = template_block_count * block_height + (template_block_count - 1) * gap

    row_template = [
        _capture_row_template(ws, 1 + i, ws.max_column) for i in range(block_height)
    ]
    # openpyxl.insert_rows() does not replicate merged-cell ranges, so capture
    # the template block's merges (relative to block start) and re-create them
    # explicitly on every newly inserted block.
    template_merges = [
        (mr.min_row - 1, mr.min_col, mr.max_row - 1, mr.max_col)
        for mr in list(ws.merged_cells.ranges)
        if mr.min_row >= 1 and mr.max_row <= block_height
    ]

    if n > template_block_count:
        extra_blocks = n - template_block_count
        insert_at = total_template_rows + 1
        _insert_rows_preserving_heights(ws, insert_at, extra_blocks * (block_height + gap))
        # Block b's content starts after its own leading gap row, not at insert_at.
        for b in range(extra_blocks):
            block_start = insert_at + gap + b * (block_height + gap)
            for i in range(block_height):
                _apply_row_template(ws, block_start + i, row_template[i])
            for r0, c0, r1, c1 in template_merges:
                ws.merge_cells(
                    start_row=block_start + r0, start_column=c0,
                    end_row=block_start + r1, end_column=c1,
                )
    elif n < template_block_count:
        # Always keep at least block 1 physically present (cleared if n == 0) —
        # card blocks are self-contained, safe to delete wholesale beyond that.
        keep = max(n, 1)
        delete_from = keep * block_height + (keep - 1) * gap + 1
        delete_count = total_template_rows - delete_from + 1
        for merged_range in list(ws.merged_cells.ranges):
            if merged_range.min_row >= delete_from:
                ws.unmerge_cells(str(merged_range))
        ws.delete_rows(delete_from, amount=delete_count)

    for offset, entry in enumerate(entries):
        block_start = 1 + offset * (block_height + gap)
        writer = card_writer or _write_contract_card_block
        writer(ws, block_start, block_height, entry)
        ctx.record(sheet_name, f"block starting row {block_start}", "spreadsheet_row", entry["file_number"])

    if n == 0:
        # Rows 1-2 (title/identifier) hold per-entry example text in column A
        # too (e.g. "JOA" / "EXAMPLE-001") — clear those alongside column B+;
        # rows 3+ column A are static field labels and stay untouched.
        for row_number in (1, 2):
            cell = ws.cell(row_number, 1)
            if not isinstance(cell, MergedCell):
                cell.value = None
        for row_number in range(1, block_height + 1):
            for col in range(2, ws.max_column + 1):
                cell = ws.cell(row_number, col)
                if not isinstance(cell, MergedCell):
                    cell.value = None

    new_total_rows = (n * block_height + (n - 1) * gap) if n > 0 else block_height
    ctx.own_rows(sheet_name, 1, max(total_template_rows, new_total_rows))
    ctx.inserted_ranges.append(
        {
            "sheet_name": sheet_name,
            "start_row": total_template_rows + 1,
            "row_count": new_total_rows - total_template_rows,
        }
    )


def _fill_agreements(wb, manifest: UnitManifest, ctx: DDRWriteContext) -> None:
    entries = [
        {"file_number": c.file_number, "record_type": c.record_type, "lessor": c.lessor, "lessee": c.lessee}
        for c in manifest.reference_contracts
        if c.record_type in _AGREEMENT_RECORD_TYPES_FOR_AGREEMENTS_TAB
    ]
    _fill_card_sheet(wb, "Agreements", AGREEMENTS_BLOCK_HEIGHT, AGREEMENTS_TEMPLATE_BLOCK_COUNT, entries, ctx)


def _fill_unit_and_pooling_agreements(wb, manifest: UnitManifest, ctx: DDRWriteContext) -> None:
    entries = [
        {
            "file_number": c.file_number,
            "record_type": c.record_type,
            "lessor": c.lessor,
            "lessee": c.lessee,
            "recording_info": c.recording_info,
            "effective_date": c.effective_date,
            "unit_description": c.unit_description,
            "formations": c.formations,
            "notes": c.notes,
        }
        for c in manifest.reference_contracts
        if c.record_type in _AGREEMENT_RECORD_TYPES_FOR_UNIT_POOLING_TAB
    ]
    _fill_card_sheet(wb, "Unit and Pooling Agreements", UNIT_POOLING_BLOCK_HEIGHT, UNIT_POOLING_TEMPLATE_BLOCK_COUNT, entries, ctx, card_writer=_write_unit_pooling_card_block)


# ---------------------------------------------------------------------------
# Audit trail (hidden, never deleted, never shown to client without an
# explicit clean-export step)
# ---------------------------------------------------------------------------

def _write_audit_trail_sheet(wb, ctx: DDRWriteContext) -> None:
    ws = wb.create_sheet("DD_Audit_Trail")
    ws.append(["Sheet", "Location", "Source Type", "Source Reference", "Confidence", "Extracted Text"])
    for row in ctx.audit_rows:
        ws.append([row.sheet, row.location, row.source_type, row.source_reference, row.confidence, row.extracted_text])
    ws.sheet_state = "hidden"


def _write_pending_items_sheet(wb, registry) -> None:
    """The "Pending Items" report: every blank the pipeline left, with the reason
    it is blank and where to look to resolve it.

    A blank cell cannot say why it is blank, and the reason must never be written
    into a client cell. This sheet is where the reader finds out — visible (not
    hidden like the audit trail), because it IS the work list.
    """
    if registry is None:
        return
    if "Pending Items" in wb.sheetnames:
        del wb["Pending Items"]
    ws = wb.create_sheet("Pending Items")
    rows = registry.report_rows()
    for row in rows:
        ws.append(row)
    header = ws[1]
    for cell in header:
        cell.font = Font(bold=True)
    for column, width in zip("ABCDEF", (22, 26, 22, 26, 18, 78)):
        ws.column_dimensions[column].width = width
    ws.freeze_panes = "A2"
    for row in ws.iter_rows(min_row=2):
        row[-1].alignment = Alignment(wrap_text=True, vertical="top")
    if len(rows) == 1:  # header only
        ws.append(["", "", "", "None", "",
                   "No pipeline-owned blanks — every client-facing cell is either "
                   "populated or explained."])
