from __future__ import annotations

from copy import copy
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from shutil import copy2
from typing import Any

from openpyxl import load_workbook
from openpyxl.formula.translate import Translator
from openpyxl.styles import PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.utils.cell import coordinate_to_tuple
from openpyxl.worksheet.worksheet import Worksheet

from src.schemas import ClassificationStatus, ProjectMetadata, SourceDocument
from src.utils import enum_value, normalize_text, read_yaml, safe_filename, timestamp, write_json


DEFAULT_TEMPLATE_MAP_PATH = Path("config/template_map.yaml")


class TemplateValidationError(RuntimeError):
    pass


@dataclass
class TemplateWriteResult:
    output_path: Path
    integrity_report_path: Path
    integrity_report: dict[str, Any]


@dataclass
class TemplateCheckResult:
    passed: bool
    sheet_name: str | None
    header_row: int | None
    column_map: dict[str, int] = field(default_factory=dict)
    missing_columns: list[str] = field(default_factory=list)
    message: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "sheet_name": self.sheet_name,
            "header_row": self.header_row,
            "column_map": self.column_map,
            "missing_columns": self.missing_columns,
            "message": self.message,
        }


def load_template_config(path: str | Path = DEFAULT_TEMPLATE_MAP_PATH) -> dict[str, Any]:
    return read_yaml(path)


def validate_template(
    template_path: str | Path,
    config: dict[str, Any] | None = None,
) -> TemplateCheckResult:
    config = config or load_template_config()
    workbook = _load_workbook(template_path)
    sheet = _find_runsheet_sheet(workbook, config)
    if not sheet:
        return TemplateCheckResult(
            passed=False,
            sheet_name=None,
            header_row=None,
            missing_columns=list(config.get("required_columns", {}).keys()),
            message="Could not find a runsheet sheet by configured names or headers.",
        )

    header_row, column_map = _find_header_row(sheet, config)
    required = set(config.get("required_columns", {}).keys())
    missing = sorted(required - set(column_map))
    passed = not missing
    message = (
        "Template check passed."
        if passed
        else f"Missing required visible PLM runsheet columns: {', '.join(missing)}"
    )
    return TemplateCheckResult(
        passed=passed,
        sheet_name=sheet.title,
        header_row=header_row,
        column_map=column_map,
        missing_columns=missing,
        message=message,
    )


def generate_runsheet(
    template_path: str | Path,
    records: list[SourceDocument],
    output_dir: str | Path,
    project_name: str = "PLM_Title_Automation",
    config: dict[str, Any] | None = None,
    metadata: ProjectMetadata | dict[str, Any] | None = None,
) -> Path:
    return generate_runsheet_with_report(
        template_path,
        records,
        output_dir,
        project_name=project_name,
        config=config,
        metadata=metadata,
    ).output_path


def generate_runsheet_with_report(
    template_path: str | Path,
    records: list[SourceDocument],
    output_dir: str | Path,
    project_name: str = "PLM_Title_Automation",
    config: dict[str, Any] | None = None,
    metadata: ProjectMetadata | dict[str, Any] | None = None,
    ownership_result: Any = None,
) -> TemplateWriteResult:
    config = config or load_template_config()
    template_path = Path(template_path)
    if not template_path.exists():
        raise TemplateValidationError(f"Template workbook does not exist: {template_path}")

    check = validate_template(template_path, config)
    if not check.passed:
        raise TemplateValidationError(check.message)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = ".xlsm" if template_path.suffix.lower() == ".xlsm" else ".xlsx"
    output_path = (
        output_dir
        / f"{safe_filename(project_name)}_preliminary_runsheet_{timestamp()}{suffix}"
    )

    source_workbook = _load_workbook(template_path)
    source_snapshot = _capture_workbook_snapshot(source_workbook)

    copy2(template_path, output_path)

    workbook = _load_workbook(output_path)
    rows = _ordered_runsheet_records(records)

    # Write to ALL runsheet sheets (NE, W2/SE, etc.).
    # Always include the validated primary sheet even if its name is non-standard.
    all_sheet_names = _find_all_runsheet_sheet_names(workbook, config)
    if check.sheet_name not in all_sheet_names:
        all_sheet_names.insert(0, check.sheet_name)

    primary_inserted_range: dict[str, Any] = {}
    for sheet_name in all_sheet_names:
        sheet = workbook[sheet_name]
        header_row, column_map = _find_header_row(sheet, config)
        if not header_row or not column_map:
            continue
        sheet_check = TemplateCheckResult(
            passed=True,
            sheet_name=sheet_name,
            header_row=header_row,
            column_map=column_map,
        )
        ir = _write_runsheet_rows(sheet, rows, sheet_check, config)
        if sheet_name == check.sheet_name:
            primary_inserted_range = ir

    # Populate Ownership Worksheet
    _write_ownership_worksheet(workbook, records, config, metadata, ownership_result)

    workbook.save(output_path)

    if not primary_inserted_range:
        primary_inserted_range = {
            "sheet_name": check.sheet_name,
            "start_row": check.header_row + 1 if check.header_row else 2,
            "end_row": check.header_row if check.header_row else 1,
            "row_count": 0,
        }

    saved_workbook = _load_workbook(output_path)
    integrity_report = _build_template_integrity_report(
        template_path=template_path,
        output_path=output_path,
        check=check,
        source_snapshot=source_snapshot,
        saved_workbook=saved_workbook,
        inserted_range=primary_inserted_range,
    )
    integrity_report_path = template_integrity_report_path(output_path)
    write_json(integrity_report_path, integrity_report)
    return TemplateWriteResult(
        output_path=output_path,
        integrity_report_path=integrity_report_path,
        integrity_report=integrity_report,
    )


def template_integrity_report_path(runsheet_path: str | Path) -> Path:
    runsheet_path = Path(runsheet_path)
    return runsheet_path.with_name(
        f"{runsheet_path.stem}_template_integrity_report.json"
    )


def _find_all_runsheet_sheet_names(workbook, config: dict[str, Any]) -> list[str]:
    """Return all sheet names that have enough runsheet columns to be written."""
    candidate_names = {normalize_text(n) for n in config.get("runsheet_sheet_names", [])}
    required = set(config.get("required_columns", {}).keys())
    result: list[str] = []
    for ws in workbook.worksheets:
        norm = normalize_text(ws.title)
        is_candidate = any(
            norm == cn or norm.startswith(f"{cn} ") or cn in norm
            for cn in candidate_names
        )
        if not is_candidate:
            continue
        _, col_map = _find_header_row(ws, config)
        if len(required & set(col_map)) >= max(len(required) - 2, 1):
            result.append(ws.title)
    return result


# ---------------------------------------------------------------------------
# Interest-type classifier for ownership worksheet
# ---------------------------------------------------------------------------

_OGL_KEYWORDS = {"lease", "leasehold", "oil and gas lease", "oil & gas lease"}
_DEED_KEYWORDS = {
    "patent", "warranty deed", "mineral deed", "quit claim deed", "quitclaim deed",
    "deed", "distribution deed", "personal representative deed", "affidavit of heirship",
    "royalty deed",
}


def _ownership_interest_type(doc_type: str | None) -> str:
    if not doc_type:
        return "Fee - OGM"
    dt = doc_type.lower()
    if any(k in dt for k in _OGL_KEYWORDS):
        return "OGL"
    if "royalty" in dt:
        return "Royalty"
    if "pooling" in dt:
        return "Pooling"
    return "Fee - OGM"


def _ownership_status(record: SourceDocument) -> str:
    ls = enum_value(record.lease_status)
    if ls in {"EXPIRED", "RELEASED"}:
        return ls.capitalize()
    return "Open"


def _fraction_to_decimal(fraction: str | None) -> float | None:
    """Convert '1/2' → 0.5, or None if not parseable."""
    if not fraction:
        return None
    try:
        parts = fraction.split("/")
        if len(parts) == 2:
            return round(int(parts[0]) / int(parts[1]), 6)
    except (ValueError, ZeroDivisionError):
        pass
    return None


def _parse_acreage(value: str | float | None) -> float | None:
    """Parse acreage string or float to float, or None if not parseable."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", ".").strip())
    except (ValueError, TypeError):
        return None


def _write_ownership_worksheet(
    workbook,
    records: list[SourceDocument],
    config: dict[str, Any],
    metadata: ProjectMetadata | dict[str, Any] | None = None,
    ownership_result: Any = None,
) -> None:
    """Populate the Ownership Worksheet from a pre-computed OwnershipResult.

    If ownership_result is None or has no entries, falls back to writing one
    row per INCLUDE record with blank interest columns (analyst to fill).
    needs_review rows are highlighted in yellow.
    """
    ownership_names = {
        normalize_text(n) for n in config.get("ownership_sheet_names", [])
    }
    ownership_ws = next(
        (ws for ws in workbook.worksheets if normalize_text(ws.title) in ownership_names),
        None,
    )
    if not ownership_ws:
        return

    own_col_aliases = config.get("ownership_columns", {})
    header_row, col_map = _find_header_row_for_aliases(ownership_ws, own_col_aliases)
    if not header_row or not col_map:
        return

    review_fill = PatternFill(
        fill_type="solid", start_color="FFEB9C", end_color="FFEB9C"
    )

    # ── Use chain-of-title entries when available ─────────────────────────
    entries = getattr(ownership_result, "entries", None) if ownership_result else None

    if entries:
        data_start = header_row + 1
        ownership_ws.insert_rows(data_start, amount=len(entries))

        for offset, entry in enumerate(entries):
            row_num = data_start + offset

            def _set(field_name: str, value: Any) -> None:
                col = col_map.get(field_name)
                if col:
                    ownership_ws.cell(row_num, col).value = value

            _set("mineral_owner", entry.party)
            _set("source_deed", entry.source_instrument or None)
            _set("interest_type", entry.interest_type)
            _set("status", entry.status)
            _set("section", entry.section)
            _set("township", entry.township)
            _set("range", entry.range_)
            _set("legal_description", entry.legal_description)
            _set("gross_acres", _parse_acreage(entry.gross_acres))
            _set("comments", entry.comments or (entry.review_note if entry.needs_review else None))

            if entry.interest_fraction and entry.interest_fraction != "?":
                dec = entry.interest_decimal
                _set("mineral_interest", dec)
                _set("executive_rights", dec)
                _set("right_to_bonus", dec)
                _set("burdens", 0)
                gross = _parse_acreage(entry.gross_acres)
                if gross is not None:
                    nma = round(gross * dec, 6)
                    _set("nma", nma)
                    _set("open_of_record", nma)

            if entry.needs_review:
                for col_num in col_map.values():
                    ownership_ws.cell(row_num, col_num).fill = review_fill
        return

    # ── Fallback: one row per INCLUDE record, blank interest columns ──────
    from datetime import date as _date
    include_statuses = {ClassificationStatus.INCLUDE_FULL, ClassificationStatus.INCLUDE_LIMITED}
    include_rows = sorted(
        (r for r in records if r.status in include_statuses),
        key=lambda r: (
            r.instrument_date or r.recording_date or _date.max,
            r.source_document_id,
        ),
    )
    if not include_rows:
        return

    if isinstance(metadata, dict):
        meta_section = metadata.get("section") or ""
        meta_township = metadata.get("township") or ""
        meta_range = metadata.get("range") or ""
    elif metadata:
        meta_section = metadata.section or ""
        meta_township = metadata.township or ""
        meta_range = metadata.range or ""
    else:
        meta_section = meta_township = meta_range = ""

    data_start = header_row + 1
    ownership_ws.insert_rows(data_start, amount=len(include_rows))

    for offset, record in enumerate(include_rows):
        row_num = data_start + offset

        def _set(field_name: str, value: Any) -> None:  # noqa: F811
            col = col_map.get(field_name)
            if col:
                ownership_ws.cell(row_num, col).value = value

        _set("mineral_owner", record.grantee)
        source_deed = record.instrument_number
        if not source_deed and record.book:
            source_deed = f"{record.book}/{record.page}" if record.page else record.book
        _set("source_deed", source_deed)
        _set("interest_type", _ownership_interest_type(record.document_type))
        _set("status", _ownership_status(record))
        _set("section", meta_section or None)
        _set("township", meta_township or None)
        _set("range", meta_range or None)
        _set("legal_description", record.legal_description)
        _set("gross_acres", _parse_acreage(record.acreage))


def _find_header_row_for_aliases(
    sheet: Worksheet,
    col_aliases: dict[str, list[str]],
    max_rows: int = 25,
) -> tuple[int | None, dict[str, int]]:
    """Find header row using a custom alias map (for ownership worksheet)."""
    best_row: int | None = None
    best_map: dict[str, int] = {}
    for row_number in range(1, min(max_rows, sheet.max_row) + 1):
        values = {
            normalize_text(str(cell.value)): cell.column
            for cell in sheet[row_number]
            if cell.value is not None
        }
        row_map: dict[str, int] = {}
        for field_name, aliases in col_aliases.items():
            for alias in aliases:
                if normalize_text(alias) in values:
                    row_map[field_name] = values[normalize_text(alias)]
                    break
        if len(row_map) > len(best_map):
            best_row = row_number
            best_map = row_map
    return best_row, best_map


def _load_workbook(path: str | Path):
    path = Path(path)
    return load_workbook(
        path,
        data_only=False,
        keep_vba=path.suffix.lower() == ".xlsm",
    )


def _find_runsheet_sheet(workbook, config: dict[str, Any]) -> Worksheet | None:
    candidate_names = {normalize_text(name) for name in config.get("runsheet_sheet_names", [])}
    for sheet in workbook.worksheets:
        sheet_name = normalize_text(sheet.title)
        if any(
            sheet_name == candidate_name or sheet_name.startswith(f"{candidate_name} ")
            for candidate_name in candidate_names
        ):
            return sheet

    best_sheet: Worksheet | None = None
    best_required_matches = 0
    for sheet in workbook.worksheets:
        header_row, column_map = _find_header_row(sheet, config)
        required_matches = len(
            set(config.get("required_columns", {}).keys()) & set(column_map)
        )
        if header_row and required_matches > best_required_matches:
            best_sheet = sheet
            best_required_matches = required_matches
    return best_sheet


def _find_header_row(
    sheet: Worksheet,
    config: dict[str, Any],
) -> tuple[int | None, dict[str, int]]:
    header_scan_rows = int(config.get("header_scan_rows", 25))
    required_columns = config.get("required_columns", {})
    optional_columns = config.get("optional_columns", {})
    all_columns = {**required_columns, **optional_columns}

    best_row: int | None = None
    best_map: dict[str, int] = {}
    for row_number in range(1, min(header_scan_rows, sheet.max_row) + 1):
        values = {
            normalize_text(cell.value): cell.column
            for cell in sheet[row_number]
            if cell.value is not None
        }
        row_map: dict[str, int] = {}
        for field_name, aliases in all_columns.items():
            for alias in aliases:
                alias_key = normalize_text(alias)
                if alias_key in values:
                    row_map[field_name] = values[alias_key]
                    break
        if len(row_map) > len(best_map):
            best_row = row_number
            best_map = row_map

    return best_row, best_map


def _ordered_runsheet_records(records: list[SourceDocument]) -> list[SourceDocument]:
    included_statuses = {
        ClassificationStatus.INCLUDE_FULL,
        ClassificationStatus.INCLUDE_LIMITED,
        ClassificationStatus.REVIEW,
    }
    included = [record for record in records if record.status in included_statuses]
    redline = [record for record in records if record.status == ClassificationStatus.REDLINE]

    included.sort(
        key=lambda record: (
            record.instrument_date or record.recording_date or date.max,
            record.source_document_id,
        )
    )
    return included + redline


def _write_runsheet_rows(
    sheet: Worksheet,
    records: list[SourceDocument],
    check: TemplateCheckResult,
    config: dict[str, Any],
) -> dict[str, Any]:
    start_row = int(check.header_row) + 1
    row_count = len(records)
    inserted_range = {
        "sheet_name": sheet.title,
        "start_row": start_row,
        "end_row": start_row + row_count - 1 if row_count else start_row - 1,
        "row_count": row_count,
    }
    if not records:
        return inserted_range

    row_template = _capture_row_template(
        sheet,
        start_row,
        max(sheet.max_column, max(check.column_map.values())),
    )
    row_dimensions = _capture_row_dimensions(sheet)
    sheet.insert_rows(start_row, amount=row_count)
    _restore_row_dimensions_after_insert(sheet, row_dimensions, start_row, row_count)

    redline_fill = PatternFill(
        fill_type="solid",
        start_color=config.get("redline_fill", "FFC7CE"),
        end_color=config.get("redline_fill", "FFC7CE"),
    )
    review_fill = PatternFill(
        fill_type="solid",
        start_color=config.get("review_fill", "FFEB9C"),
        end_color=config.get("review_fill", "FFEB9C"),
    )

    for offset, record in enumerate(records):
        row_number = start_row + offset
        _apply_row_template(sheet, row_number, row_template)
        values = _record_to_runsheet_values(record, sequence_number=offset + 1)
        for field_name, column_number in check.column_map.items():
            if field_name in values:
                sheet.cell(row=row_number, column=column_number).value = values[field_name]
        if record.status == ClassificationStatus.REDLINE:
            for column_number in check.column_map.values():
                sheet.cell(row=row_number, column=column_number).fill = redline_fill
        elif record.status == ClassificationStatus.REVIEW:
            for column_number in check.column_map.values():
                sheet.cell(row=row_number, column=column_number).fill = review_fill
    return inserted_range


def _record_to_runsheet_values(
    record: SourceDocument,
    sequence_number: int | None = None,
) -> dict[str, Any]:
    return {
        "sequence_number": sequence_number,
        "effective_date": record.effective_date
        or record.instrument_date
        or record.recording_date,
        "instrument_date": record.instrument_date,
        "recording_date": record.recording_date,
        "document_type": record.document_type or record.document_title,
        "grantor": record.grantor,
        "grantee": record.grantee,
        "book": record.book,
        "page": record.page,
        "instrument_number": _formatted_instrument_number(record),
        "comments": _runsheet_comments(record),
        "conveyance": record.conveyance or record.legal_description,
        "acreage": record.acreage,
    }


def _formatted_instrument_number(record: SourceDocument) -> str | None:
    parts = []
    if record.book and record.page:
        parts.append(f"{record.book}/{record.page}")
    elif record.book:
        parts.append(str(record.book))
    elif record.page:
        parts.append(str(record.page))
    if record.instrument_number:
        parts.append(str(record.instrument_number))
    return "\n".join(part for part in parts if part) or None


def _runsheet_comments(record: SourceDocument) -> str | None:
    """COMMENTS column: title analysis only.

    Contains record.comments (from OCR/title_extractor: reservations, OGL terms, etc.)
    and EXPIRED/RELEASED lease status. Review flags and redline reasons live in
    QA_EXCEPTION_LOG and the review_checklist — not in the client deliverable.
    """
    comments: list[str] = []
    if record.comments:
        comments.append(str(record.comments))

    lease_status = enum_value(record.lease_status)
    if lease_status in {"EXPIRED", "RELEASED"}:
        comments.append(lease_status)

    deduped: list[str] = []
    seen: set[str] = set()
    for comment in comments:
        comment = comment.strip()
        key = normalize_text(comment)
        if comment and key not in seen:
            deduped.append(comment)
            seen.add(key)
    return "\n\n".join(deduped) or None


def _capture_row_template(
    sheet: Worksheet,
    row_number: int,
    max_column: int,
) -> dict[str, Any]:
    cells: dict[int, dict[str, Any]] = {}
    for column_number in range(1, max_column + 1):
        cell = sheet.cell(row=row_number, column=column_number)
        cells[column_number] = {
            "origin": cell.coordinate,
            "value": cell.value,
            "font": copy(cell.font),
            "fill": copy(cell.fill),
            "border": copy(cell.border),
            "alignment": copy(cell.alignment),
            "number_format": cell.number_format,
            "protection": copy(cell.protection),
        }
    return {
        "row_number": row_number,
        "row_dimension": _row_dimension_signature(sheet.row_dimensions[row_number]),
        "cells": cells,
    }


def _apply_row_template(
    sheet: Worksheet,
    row_number: int,
    row_template: dict[str, Any],
) -> None:
    _apply_row_dimension(
        sheet.row_dimensions[row_number],
        row_template["row_dimension"],
    )
    for column_number, style in row_template["cells"].items():
        cell = sheet.cell(row=row_number, column=column_number)
        value = style["value"]
        if isinstance(value, str) and value.startswith("="):
            value = _translate_formula(value, style["origin"], cell.coordinate)
        else:
            value = copy(value)
        cell.value = value
        cell.font = copy(style["font"])
        cell.fill = copy(style["fill"])
        cell.border = copy(style["border"])
        cell.alignment = copy(style["alignment"])
        cell.number_format = style["number_format"]
        cell.protection = copy(style["protection"])


def _translate_formula(formula: str, origin: str, target: str) -> str:
    try:
        return Translator(formula, origin=origin).translate_formula(target)
    except Exception:
        return formula


def _capture_row_dimensions(sheet: Worksheet) -> dict[int, dict[str, Any]]:
    return {
        row_number: _row_dimension_signature(sheet.row_dimensions[row_number])
        for row_number in range(1, sheet.max_row + 1)
    }


def _restore_row_dimensions_after_insert(
    sheet: Worksheet,
    row_dimensions: dict[int, dict[str, Any]],
    start_row: int,
    inserted_count: int,
) -> None:
    template_dimension = row_dimensions.get(start_row, {})
    for row_number in range(1, sheet.max_row + 1):
        if start_row <= row_number < start_row + inserted_count:
            dimension = template_dimension
        else:
            source_row = (
                row_number if row_number < start_row else row_number - inserted_count
            )
            dimension = row_dimensions.get(source_row, {})
        _apply_row_dimension(sheet.row_dimensions[row_number], dimension)


def _row_dimension_signature(row_dimension) -> dict[str, Any]:
    return {
        "height": row_dimension.height,
        "hidden": row_dimension.hidden,
        "outline_level": row_dimension.outlineLevel,
        "collapsed": row_dimension.collapsed,
    }


def _apply_row_dimension(row_dimension, signature: dict[str, Any]) -> None:
    row_dimension.height = signature.get("height")
    row_dimension.hidden = bool(signature.get("hidden", False))
    row_dimension.outlineLevel = int(signature.get("outline_level") or 0)
    row_dimension.collapsed = bool(signature.get("collapsed", False))


def _capture_workbook_snapshot(workbook) -> dict[str, Any]:
    return {
        "sheet_names": workbook.sheetnames,
        "sheets": {
            sheet.title: {
                "sheet_state": sheet.sheet_state,
                "freeze_panes": str(sheet.freeze_panes) if sheet.freeze_panes else None,
                "auto_filter_ref": sheet.auto_filter.ref,
                "max_row": sheet.max_row,
                "max_column": sheet.max_column,
                "merged_ranges": sorted(
                    str(range_item) for range_item in sheet.merged_cells.ranges
                ),
                "column_dimensions": _capture_column_dimensions(sheet),
                "row_dimensions": _capture_row_dimensions(sheet),
                "cell_styles": _capture_cell_styles(sheet),
                "formulas": _capture_formulas(sheet),
            }
            for sheet in workbook.worksheets
        },
    }


def _capture_column_dimensions(sheet: Worksheet) -> dict[str, dict[str, Any]]:
    columns = {
        get_column_letter(column_number)
        for column_number in range(1, sheet.max_column + 1)
    }
    columns.update(sheet.column_dimensions.keys())
    return {
        column_letter: {
            "width": sheet.column_dimensions[column_letter].width,
            "hidden": sheet.column_dimensions[column_letter].hidden,
            "outline_level": sheet.column_dimensions[column_letter].outlineLevel,
            "collapsed": sheet.column_dimensions[column_letter].collapsed,
        }
        for column_letter in sorted(columns)
    }


def _capture_cell_styles(sheet: Worksheet) -> dict[str, dict[str, Any]]:
    styles: dict[str, dict[str, Any]] = {}
    for row in sheet.iter_rows():
        for cell in row:
            if cell.value is not None or cell.has_style:
                styles[cell.coordinate] = _cell_style_signature(cell)
    return styles


def _capture_formulas(sheet: Worksheet) -> dict[str, str]:
    formulas: dict[str, str] = {}
    for row in sheet.iter_rows():
        for cell in row:
            if isinstance(cell.value, str) and cell.value.startswith("="):
                formulas[cell.coordinate] = cell.value
    return formulas


def _cell_style_signature(cell) -> dict[str, Any]:
    return {
        "font": {
            "name": cell.font.name,
            "size": cell.font.sz,
            "bold": cell.font.b,
            "italic": cell.font.i,
            "underline": cell.font.u,
            "strike": cell.font.strike,
            "color": _color_signature(cell.font.color),
        },
        "fill": {
            "fill_type": cell.fill.fill_type,
            "fg_color": _color_signature(cell.fill.fgColor),
            "bg_color": _color_signature(cell.fill.bgColor),
        },
        "border": {
            "left": _side_signature(cell.border.left),
            "right": _side_signature(cell.border.right),
            "top": _side_signature(cell.border.top),
            "bottom": _side_signature(cell.border.bottom),
        },
        "alignment": {
            "horizontal": cell.alignment.horizontal,
            "vertical": cell.alignment.vertical,
            "text_rotation": cell.alignment.textRotation,
            "wrap_text": cell.alignment.wrap_text,
            "shrink_to_fit": cell.alignment.shrink_to_fit,
            "indent": cell.alignment.indent,
        },
        "number_format": cell.number_format,
        "protection": {
            "locked": cell.protection.locked,
            "hidden": cell.protection.hidden,
        },
    }


def _side_signature(side) -> dict[str, Any]:
    if side is None:
        return {"style": None, "color": None}
    return {
        "style": side.style,
        "color": _color_signature(side.color),
    }


def _color_signature(color) -> str | None:
    if color is None:
        return None
    if color.type == "rgb":
        return color.rgb
    if color.type == "indexed":
        return f"indexed:{color.indexed}"
    if color.type == "theme":
        return f"theme:{color.theme}:{color.tint}"
    if color.type == "auto":
        return "auto"
    return str(color)


def _build_template_integrity_report(
    template_path: Path,
    output_path: Path,
    check: TemplateCheckResult,
    source_snapshot: dict[str, Any],
    saved_workbook,
    inserted_range: dict[str, Any],
    additional_inserted_ranges: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """additional_inserted_ranges lets a multi-sheet writer (e.g. ddr_writer.py)
    report one inserted_range per touched sheet. MOR's single-sheet call site
    keeps passing only `inserted_range`, unchanged."""
    saved_snapshot = _capture_workbook_snapshot(saved_workbook)
    inserted_ranges = [inserted_range] + list(additional_inserted_ranges or [])
    column_diffs = _compare_column_dimensions(source_snapshot, saved_snapshot)
    row_height_diffs = _compare_row_heights(
        source_snapshot,
        saved_snapshot,
        inserted_ranges,
    )
    formula_diffs = _compare_formulas(
        source_snapshot,
        saved_snapshot,
        inserted_ranges,
    )
    style_diffs = _compare_cell_styles(
        source_snapshot,
        saved_snapshot,
        inserted_ranges,
    )

    checks = {
        "template_file_copied_before_edit": output_path.exists(),
        "workbook_not_created_from_scratch": True,
        "sheet_names_preserved": source_snapshot["sheet_names"]
        == saved_snapshot["sheet_names"],
        "column_widths_preserved": not column_diffs,
        "row_heights_outside_inserted_range_preserved": not row_height_diffs,
        "styles_outside_inserted_range_preserved": not style_diffs["all"],
        "wrap_text_outside_inserted_range_preserved": not style_diffs["wrap_text"],
        "borders_outside_inserted_range_preserved": not style_diffs["border"],
        "number_formats_outside_inserted_range_preserved": not style_diffs[
            "number_format"
        ],
        "formulas_outside_inserted_range_preserved": not formula_diffs,
    }

    return {
        "passed": all(checks.values()),
        "generated_at": timestamp(),
        "template_path": str(template_path),
        "output_path": str(output_path),
        "template_check": check.as_dict(),
        "inserted_range": inserted_range,
        "inserted_ranges": inserted_ranges,
        "checks": checks,
        "diffs": {
            "column_dimensions": _limit_diffs(column_diffs),
            "row_heights": _limit_diffs(row_height_diffs),
            "formulas": _limit_diffs(formula_diffs),
            "styles": _limit_diffs(style_diffs["all"]),
            "wrap_text": _limit_diffs(style_diffs["wrap_text"]),
            "borders": _limit_diffs(style_diffs["border"]),
            "number_formats": _limit_diffs(style_diffs["number_format"]),
        },
    }


def _compare_column_dimensions(
    source_snapshot: dict[str, Any],
    saved_snapshot: dict[str, Any],
) -> list[dict[str, Any]]:
    diffs: list[dict[str, Any]] = []
    for sheet_name, source_sheet in source_snapshot["sheets"].items():
        saved_sheet = saved_snapshot["sheets"].get(sheet_name)
        if not saved_sheet:
            diffs.append({"sheet": sheet_name, "issue": "missing sheet"})
            continue
        for column, source_dimension in source_sheet["column_dimensions"].items():
            saved_dimension = saved_sheet["column_dimensions"].get(column)
            if source_dimension != saved_dimension:
                diffs.append(
                    {
                        "sheet": sheet_name,
                        "column": column,
                        "expected": source_dimension,
                        "actual": saved_dimension,
                    }
                )
    return diffs


def _compare_row_heights(
    source_snapshot: dict[str, Any],
    saved_snapshot: dict[str, Any],
    inserted_ranges: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    diffs: list[dict[str, Any]] = []
    for sheet_name, source_sheet in source_snapshot["sheets"].items():
        saved_sheet = saved_snapshot["sheets"].get(sheet_name)
        if not saved_sheet:
            diffs.append({"sheet": sheet_name, "issue": "missing sheet"})
            continue
        for row_number, source_dimension in source_sheet["row_dimensions"].items():
            expected_row = _translated_row(sheet_name, row_number, inserted_ranges)
            saved_dimension = saved_sheet["row_dimensions"].get(expected_row, {})
            if source_dimension.get("height") != saved_dimension.get("height"):
                diffs.append(
                    {
                        "sheet": sheet_name,
                        "row": expected_row,
                        "source_row": row_number,
                        "expected": source_dimension.get("height"),
                        "actual": saved_dimension.get("height"),
                    }
                )
    return diffs


def _compare_formulas(
    source_snapshot: dict[str, Any],
    saved_snapshot: dict[str, Any],
    inserted_ranges: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    diffs: list[dict[str, Any]] = []
    for sheet_name, source_sheet in source_snapshot["sheets"].items():
        saved_sheet = saved_snapshot["sheets"].get(sheet_name)
        if not saved_sheet:
            diffs.append({"sheet": sheet_name, "issue": "missing sheet"})
            continue
        for coordinate, source_formula in source_sheet["formulas"].items():
            expected_coordinate = _translated_coordinate(
                sheet_name,
                coordinate,
                inserted_ranges,
            )
            saved_formula = saved_sheet["formulas"].get(expected_coordinate)
            if source_formula != saved_formula:
                diffs.append(
                    {
                        "sheet": sheet_name,
                        "cell": expected_coordinate,
                        "source_cell": coordinate,
                        "expected": source_formula,
                        "actual": saved_formula,
                    }
                )
    return diffs


def _compare_cell_styles(
    source_snapshot: dict[str, Any],
    saved_snapshot: dict[str, Any],
    inserted_ranges: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    diffs: dict[str, list[dict[str, Any]]] = {
        "all": [],
        "wrap_text": [],
        "border": [],
        "number_format": [],
    }
    for sheet_name, source_sheet in source_snapshot["sheets"].items():
        saved_sheet = saved_snapshot["sheets"].get(sheet_name)
        if not saved_sheet:
            issue = {"sheet": sheet_name, "issue": "missing sheet"}
            for diff_list in diffs.values():
                diff_list.append(issue)
            continue
        for coordinate, source_style in source_sheet["cell_styles"].items():
            expected_coordinate = _translated_coordinate(
                sheet_name,
                coordinate,
                inserted_ranges,
            )
            saved_style = saved_sheet["cell_styles"].get(expected_coordinate)
            if source_style != saved_style:
                diffs["all"].append(
                    {
                        "sheet": sheet_name,
                        "cell": expected_coordinate,
                        "source_cell": coordinate,
                    }
                )
            _compare_style_component(
                diffs,
                "wrap_text",
                sheet_name,
                coordinate,
                expected_coordinate,
                _nested_get(source_style, "alignment", "wrap_text"),
                _nested_get(saved_style, "alignment", "wrap_text"),
            )
            _compare_style_component(
                diffs,
                "border",
                sheet_name,
                coordinate,
                expected_coordinate,
                source_style.get("border"),
                saved_style.get("border") if saved_style else None,
            )
            _compare_style_component(
                diffs,
                "number_format",
                sheet_name,
                coordinate,
                expected_coordinate,
                source_style.get("number_format"),
                saved_style.get("number_format") if saved_style else None,
            )
    return diffs


def _compare_style_component(
    diffs: dict[str, list[dict[str, Any]]],
    component: str,
    sheet_name: str,
    source_coordinate: str,
    expected_coordinate: str,
    expected: Any,
    actual: Any,
) -> None:
    if expected != actual:
        diffs[component].append(
            {
                "sheet": sheet_name,
                "cell": expected_coordinate,
                "source_cell": source_coordinate,
                "expected": expected,
                "actual": actual,
            }
        )


def _nested_get(payload: dict[str, Any] | None, *keys: str) -> Any:
    value: Any = payload
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _translated_coordinate(
    sheet_name: str,
    coordinate: str,
    inserted_ranges: list[dict[str, Any]],
) -> str:
    row_number, column_number = coordinate_to_tuple(coordinate)
    return f"{get_column_letter(column_number)}{_translated_row(sheet_name, row_number, inserted_ranges)}"


def _translated_row(
    sheet_name: str,
    row_number: int,
    inserted_ranges: list[dict[str, Any]],
) -> int:
    for inserted_range in inserted_ranges:
        if (
            sheet_name == inserted_range.get("sheet_name")
            and row_number >= inserted_range.get("start_row", float("inf"))
        ):
            return row_number + inserted_range.get("row_count", 0)
    return row_number


def _limit_diffs(diffs: list[dict[str, Any]], limit: int = 50) -> list[dict[str, Any]]:
    return diffs[:limit]
