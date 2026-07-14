"""Route a flat pile of uploaded files (DD mode "Documents" + "Template" drop
zones) into the typed inputs run_dd_pipeline_for_unit() needs: the 3 reference
workbooks (Project Log / Xref / Well List), the DDR template, the title
opinion PDFs (matched to xref file numbers), and the supplemental instrument
PDFs (everything else), turning the latter into SourceDocument records
without requiring a separate document-list spreadsheet.

This module exists because the DD frontend's "Documents" drop zone accepts
title opinions, supplemental instruments, AND the 3 reference workbooks in
one pile — there is no per-file-type upload slot in the UI. Detection is by
file extension + xlsx sheet-name sniffing, never by filename guessing alone.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import openpyxl

from src.dd.manifest import TitleOpinionRef, UnitManifest
from src.dd.manifest_builder import PROJECT_LOG_SHEET, WELLS_SHEET, XREF_SHEET
from src.pdf_reader import apply_extraction_to_record, extract_document
from src.schemas import SourceDocument
from src.utils import get_logger

logger = get_logger(__name__)

# Fallback title-opinion filename convention (e.g. "T0140045...") used only
# when no Xref workbook is available to confirm real file numbers.
_TITLE_OPINION_FILENAME_RE = re.compile(r"^T0\d{4,}", re.IGNORECASE)

# Client's descriptive title-opinion filenames don't carry the xref file
# number — they read "T-O ORIG ...", "T-O SUPP ...", "T-O SECOND SUPP ...", or
# spell out "TITLE OPINION". Used to recognize a loose PDF as a title opinion
# (rather than a supplemental instrument) when its name has no T0##### prefix.
_TITLE_OPINION_HINT_RE = re.compile(
    r"(^T0\d{4,})|(\bT[\-\s]?O\b)|(TITLE\s+OPINION)", re.IGNORECASE
)


def _looks_like_title_opinion(stem: str) -> bool:
    return bool(_TITLE_OPINION_HINT_RE.search(stem))


class RoutingError(RuntimeError):
    pass


@dataclass
class RoutedFiles:
    project_log_path: Path | None = None
    xref_path: Path | None = None
    well_list_path: Path | None = None
    ddr_template_path: Path | None = None
    title_opinion_pdfs: dict[str, Path] = field(default_factory=dict)  # file_number -> path
    instrument_pdfs: list[Path] = field(default_factory=list)
    unrouted: list[Path] = field(default_factory=list)


def _sheet_names(path: Path) -> set[str]:
    try:
        wb = openpyxl.load_workbook(path, read_only=True)
        names = set(wb.sheetnames)
        wb.close()
        return names
    except Exception as exc:  # corrupt/non-xlsx file dropped in by mistake
        logger.warning("Could not read workbook sheets for %s: %s", path, exc)
        return set()


def route_reference_workbooks(
    xlsx_paths: list[Path],
    ddr_template_path: Path,
) -> tuple[Path, Path, Path]:
    """Identify Project Log / Xref / Well List among the xlsx files dropped
    into "Documents" (the DDR template itself arrives separately, from the
    "Template" drop zone, and is never sniffed here)."""
    project_log = xref = well_list = None
    for path in xlsx_paths:
        if path == ddr_template_path:
            continue
        sheets = _sheet_names(path)
        if PROJECT_LOG_SHEET in sheets and project_log is None:
            project_log = path
        elif WELLS_SHEET in sheets and well_list is None:
            well_list = path
        elif XREF_SHEET in sheets and well_list is None and PROJECT_LOG_SHEET not in sheets:
            # Sheet1 is a generic name; only trust it once Project Log/Wells
            # are ruled out, to avoid mis-routing the Well List workbook.
            if xref is None:
                xref = path

    missing = [
        name
        for name, value in (
            ("Project Log", project_log),
            ("Xref", xref),
            ("Well List", well_list),
        )
        if value is None
    ]
    if missing:
        raise RoutingError(
            f"Could not identify the following reference workbook(s) among the "
            f"uploaded files: {', '.join(missing)}. Expected sheet names: "
            f"'{PROJECT_LOG_SHEET}' (Project Log), '{XREF_SHEET}' (Xref), "
            f"'{WELLS_SHEET}' (Well List)."
        )
    return project_log, xref, well_list


def list_unit_names(project_log_path: Path) -> list[str]:
    """Distinct unit names from Project Log column E (the same column
    manifest_builder._load_project_log matches on), in first-seen order."""
    wb = openpyxl.load_workbook(project_log_path, read_only=True, data_only=True)
    ws = wb[PROJECT_LOG_SHEET]
    seen: dict[str, None] = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        unit_cell = row[4]  # column E
        if unit_cell and str(unit_cell).strip():
            seen.setdefault(str(unit_cell).strip(), None)
    wb.close()
    return list(seen.keys())


def list_all_title_opinion_file_numbers(xref_path: Path) -> set[str]:
    """All distinct title-opinion file numbers (xref column O, well/contract
    number) across every unit in the Xref workbook — used to match uploaded
    PDF filenames before any single unit's manifest has been built."""
    wb = openpyxl.load_workbook(xref_path, read_only=True, data_only=True)
    ws = wb[XREF_SHEET]
    numbers: set[str] = set()
    for row in ws.iter_rows(min_row=2, values_only=True):
        record_type3 = str(row[17] or "").strip().upper()
        well_or_contract_nb = row[14]
        if record_type3 == "TITLE OPINIONS" and well_or_contract_nb:
            numbers.add(str(well_or_contract_nb))
    wb.close()
    return numbers


def route_uploaded_files(
    all_paths: list[Path],
    ddr_template_path: Path,
    xref_file_numbers: set[str],
) -> RoutedFiles:
    """Split the "Documents" pile into reference workbooks, title opinion
    PDFs (matched by filename containing a known xref file number), and
    supplemental instrument PDFs (every other PDF)."""
    xlsx_paths = [p for p in all_paths if p.suffix.lower() in (".xlsx", ".xlsm")]
    pdf_paths = [p for p in all_paths if p.suffix.lower() == ".pdf"]
    other = [p for p in all_paths if p not in xlsx_paths and p not in pdf_paths]

    project_log, xref, well_list = route_reference_workbooks(xlsx_paths, ddr_template_path)

    routed = RoutedFiles(
        project_log_path=project_log,
        xref_path=xref,
        well_list_path=well_list,
        ddr_template_path=ddr_template_path,
        unrouted=other,
    )

    for pdf_path in pdf_paths:
        # Mirror manifest_builder._probe_pdf_availability's own glob pattern
        # (f"{file_number}*") exactly, so routing and manifest-building agree
        # on which PDFs are title opinions.
        stem = pdf_path.stem
        matched_number = next(
            (number for number in xref_file_numbers if number and stem.startswith(number)),
            None,
        )
        if matched_number:
            routed.title_opinion_pdfs[matched_number] = pdf_path
        elif _looks_like_title_opinion(stem):
            # Descriptively-named TO PDF (e.g. "T-O ORIG BOWEN A-1449...") with
            # no xref file-number prefix — key it by a sanitized stem so it is
            # still handed to the parser rather than treated as an instrument.
            key = re.sub(r"[^A-Za-z0-9\-]", "_", stem)[:60]
            routed.title_opinion_pdfs[key] = pdf_path
        else:
            routed.instrument_pdfs.append(pdf_path)

    return routed


def build_supplemental_records_from_pdfs(
    pdf_paths: list[Path],
    work_dir: Path,
    progress_callback: Any = None,
) -> list[SourceDocument]:
    """Build a minimal SourceDocument per supplemental instrument PDF with no
    upstream document-list spreadsheet, using the same regex-based field
    extraction MOR uses to enrich records post-OCR (src/pdf_reader.py). The
    record then flows through classify_documents / apply_supplemental_scope_filter
    / run_qa exactly like a MOR-sourced record would."""
    text_cache_dir = work_dir / "ocr_cache"
    extracted_text_dir = work_dir / "extracted_text"
    records: list[SourceDocument] = []

    for row_number, pdf_path in enumerate(sorted(pdf_paths), start=1):
        doc_id = f"DD-INSTR-{row_number:04d}"
        record = SourceDocument(
            source_document_id=doc_id,
            source_row_number=row_number,
            source_file_name=pdf_path.name,
            original_file_name=pdf_path.name,
            instrument_number=pdf_path.stem,
            matched_source_file=str(pdf_path),
            source_match_method="filename_direct",
            source_match_confidence=1.0,
        )
        try:
            extraction = extract_document(pdf_path, text_cache_dir=text_cache_dir)
            apply_extraction_to_record(record, extraction, extracted_text_dir=extracted_text_dir)
            if progress_callback:
                progress_callback(
                    "ok" if extraction.extraction_status == "TEXT_EXTRACTED" else "warn",
                    f"Instrument {pdf_path.stem} — text extracted "
                    f"({extraction.extraction_status}, confidence "
                    f"{extraction.extraction_confidence:.0%})",
                )
        except Exception as exc:
            record.pdf_extraction_status = "EXTRACTION_ERROR"
            record.source_trace["pdf_extraction_error"] = str(exc)
            if progress_callback:
                progress_callback("err", f"Instrument {pdf_path.stem} — extraction failed: {exc}")
        records.append(record)

    return records


def route_uploaded_files_without_xref(
    all_paths: list[Path],
    ddr_template_path: Path,
) -> RoutedFiles:
    """Fallback routing for when no Xref/Project Log/Well List were uploaded:
    classify PDFs as title opinions purely by the client's filename
    convention (file numbers starting "T0" followed by digits — e.g.
    "T0140045..."). Everything else PDF is treated as a supplemental
    instrument. No reference workbooks are populated."""
    pdf_paths = [p for p in all_paths if p.suffix.lower() == ".pdf"]
    other = [
        p for p in all_paths
        if p.suffix.lower() not in (".pdf",) and p != ddr_template_path
    ]

    routed = RoutedFiles(ddr_template_path=ddr_template_path, unrouted=other)
    for pdf_path in pdf_paths:
        m = _TITLE_OPINION_FILENAME_RE.match(pdf_path.stem)
        if m:
            file_number = m.group(0).upper()
        else:
            # No T0XXXXX prefix — use a sanitized stem as file number so the
            # PDF is still treated as a title opinion in lite mode (no XREF to
            # distinguish TOs from instruments, so assume all PDFs are TOs).
            file_number = re.sub(r"[^A-Za-z0-9\-]", "_", pdf_path.stem)[:40]
        routed.title_opinion_pdfs[file_number] = pdf_path
    return routed


def merge_multipart_title_opinion_pdfs(document_paths: list[Path], work_dir: Path) -> list[Path]:
    """When a title opinion arrives as several PDF parts (e.g. 4 pages of scans
    uploaded as separate files all named 'T0141486 - part1.pdf', 'T0141486 - part2.pdf'
    …), merge each group into a single PDF so the parser receives one coherent
    document per file number.  Non-TO PDFs and non-PDF files pass through unchanged."""
    import fitz  # PyMuPDF

    groups: dict[str, list[Path]] = {}
    non_to: list[Path] = []

    for p in document_paths:
        if p.suffix.lower() != ".pdf":
            non_to.append(p)
            continue
        m = _TITLE_OPINION_FILENAME_RE.match(p.stem)
        if m:
            key = m.group(0).upper()
            groups.setdefault(key, []).append(p)
        else:
            non_to.append(p)

    merged_dir = work_dir / "_merged_tos"
    result: list[Path] = list(non_to)

    for file_number, parts in sorted(groups.items()):
        parts_sorted = sorted(parts)
        if len(parts_sorted) == 1:
            result.append(parts_sorted[0])
            continue
        merged_dir.mkdir(parents=True, exist_ok=True)
        merged_path = merged_dir / f"{file_number}.pdf"
        if not merged_path.exists():
            doc = fitz.open()
            for part in parts_sorted:
                with fitz.open(str(part)) as src:
                    doc.insert_pdf(src)
            doc.save(str(merged_path))
            doc.close()
        result.append(merged_path)

    return result


def build_lite_manifest(unit_name: str, title_opinion_pdfs: dict[str, Path]) -> UnitManifest:
    """A manifest built only from title-opinion filenames, for runs with no
    Project Log/Xref/Well List. confirm_coverage defaults True (unconfirmed
    by a real Xref match, but nothing to contradict it either) — note that
    this is weaker evidence than a real manifest's confirm_coverage and
    should read as "assumed in scope" rather than "verified in scope"."""
    return UnitManifest(
        unit_name=unit_name,
        title_opinions=[
            TitleOpinionRef(
                file_number=file_number,
                match_method="filename_convention_no_xref",
                confirm_coverage=True,
                pdf_available=True,
                pdf_path=str(path),
            )
            for file_number, path in sorted(title_opinion_pdfs.items())
        ],
    )
