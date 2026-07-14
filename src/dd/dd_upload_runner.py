"""Entry point for the DD frontend's RUN button: takes the flat pile of
uploaded files (Documents + Template, already saved to disk by the UI layer)
and an optional free-text instructions string, routes them, discovers every
unit in the Project Log, and runs run_dd_pipeline_for_unit() once per unit —
emitting progress events the whole way so a live feed can render in real
time.

If no Project Log/Xref/Well List were uploaded, falls back to a single
"lite" unit built from title-opinion filenames alone (no Well List
reconciliation in that mode — see intake_router.build_lite_manifest).

This is the only DD module the frontend should import directly.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.dd.dd_pipeline import DDPipelineResult, ProgressCallback, run_dd_pipeline_for_unit
from src.dd.intake_router import (
    RoutedFiles,
    RoutingError,
    build_lite_manifest,
    build_supplemental_records_from_pdfs,
    list_all_title_opinion_file_numbers,
    list_unit_names,
    merge_multipart_title_opinion_pdfs,
    route_uploaded_files,
    route_uploaded_files_without_xref,
)
from src.utils import get_logger

logger = get_logger(__name__)

# Project Log's unit_name convention is "<NAME> UNIT" (e.g. "BOWEN A UNIT") —
# the word comes after the name, not before — so this is checked first.
_UNIT_NAME_SUFFIX_RE = re.compile(r"\b([A-Z][A-Z0-9 &\-]{1,40}?\s+UNIT)\b")
_UNIT_NAME_PREFIX_RE = re.compile(r"(?:unit|project)\s*[:\-]?\s*([A-Z][A-Z0-9 _\-]{2,40})", re.IGNORECASE)


@dataclass
class UnitRunOutcome:
    unit_name: str
    result: DDPipelineResult | None = None
    error: str | None = None


@dataclass
class DDUploadRunResult:
    routed: RoutedFiles
    unit_outcomes: list[UnitRunOutcome] = field(default_factory=list)
    fatal_error: str | None = None


def _guess_unit_name(instructions_text: str, ddr_template_path: Path) -> str:
    text = instructions_text or ""
    match = _UNIT_NAME_SUFFIX_RE.search(text)
    if match:
        return re.sub(r"\s+", " ", match.group(1).strip())
    match = _UNIT_NAME_PREFIX_RE.search(text)
    if match:
        return match.group(1).strip()
    return ddr_template_path.stem


def run_dd_upload(
    document_paths: list[Path],
    ddr_template_path: Path,
    output_root: str | Path,
    instructions_text: str = "",
    progress_callback: ProgressCallback | None = None,
    unit_name_filter: str | None = None,
) -> DDUploadRunResult:
    output_root = Path(output_root)

    def emit(icon: str, message: str) -> None:
        if progress_callback:
            progress_callback(icon, message)

    emit("working", "Sorting uploaded files (reference workbooks, title opinions, instruments)...")
    merge_work = output_root / "_merge_work"
    document_paths = merge_multipart_title_opinion_pdfs(document_paths, merge_work)
    try:
        # First pass: route reference workbooks only, so we can read all xref
        # file numbers before classifying PDFs as title-opinion vs. instrument.
        routed = route_uploaded_files(document_paths, ddr_template_path, xref_file_numbers=set())
        xref_numbers = list_all_title_opinion_file_numbers(routed.xref_path)
        routed = route_uploaded_files(document_paths, ddr_template_path, xref_file_numbers=xref_numbers)
    except RoutingError as exc:
        emit(
            "warn",
            f"No Project Log/Xref/Well List found ({exc}); falling back to filename-based "
            f"title-opinion detection. WI/NRI reconciliation against a Well List will be skipped.",
        )
        return _run_lite(document_paths, ddr_template_path, output_root, instructions_text, emit, progress_callback)

    emit(
        "ok",
        f"Files sorted — Project Log, Xref, Well List identified; "
        f"{len(routed.title_opinion_pdfs)} title opinion PDF(s), "
        f"{len(routed.instrument_pdfs)} instrument PDF(s)",
    )

    try:
        unit_names = list_unit_names(routed.project_log_path)
    except Exception as exc:
        emit("err", f"Could not read unit list from Project Log: {exc}")
        return DDUploadRunResult(routed=routed, fatal_error=str(exc))

    if not unit_names:
        emit("err", "No units found in Project Log column E.")
        return DDUploadRunResult(routed=routed, fatal_error="No units found in Project Log.")

    emit("ok", f"{len(unit_names)} unit(s) found in Project Log: {', '.join(unit_names)}")

    if unit_name_filter:
        matched = [u for u in unit_names if u.upper() == unit_name_filter.upper()]
        if not matched:
            emit("err", f"Unit '{unit_name_filter}' not found in Project Log. Available: {', '.join(unit_names)}")
            return DDUploadRunResult(routed=routed, fatal_error=f"Unit '{unit_name_filter}' not found.")
        unit_names = matched
        emit("ok", f"Filtering to unit: {unit_names[0]}")

    # Title opinion PDFs all live in one shared directory so manifest_builder's
    # glob(f"{file_number}*") can find them regardless of which unit owns them.
    to_files_dir = next(iter(routed.title_opinion_pdfs.values())).parent if routed.title_opinion_pdfs else None

    # In single-unit mode, every uploaded TO PDF belongs to that unit — bind
    # them directly so descriptively-named PDFs (no xref file number) still get
    # parsed. Not done in multi-unit mode, where PDFs must be attributed to a
    # specific unit by their file-number prefix instead.
    uploaded_to_pdfs = (
        list(routed.title_opinion_pdfs.values()) if unit_name_filter else None
    )
    if uploaded_to_pdfs:
        emit("ok", f"{len(uploaded_to_pdfs)} title opinion PDF(s) will be bound to {unit_names[0]}")

    supplemental_records = _build_supplemental_records(routed, output_root, emit)

    outcomes: list[UnitRunOutcome] = []
    for unit_name in unit_names:
        try:
            result = run_dd_pipeline_for_unit(
                unit_name=unit_name,
                project_log_path=routed.project_log_path,
                xref_path=routed.xref_path,
                well_list_path=routed.well_list_path,
                ddr_template_path=ddr_template_path,
                output_root=output_root,
                to_files_dir=to_files_dir,
                supplemental_records=supplemental_records,
                progress_callback=progress_callback,
                uploaded_title_opinion_pdfs=uploaded_to_pdfs,
            )
            outcomes.append(UnitRunOutcome(unit_name=unit_name, result=result))
        except Exception as exc:
            logger.warning("DD pipeline failed for unit %s: %s", unit_name, exc)
            emit("err", f"Unit {unit_name} — failed: {exc}")
            outcomes.append(UnitRunOutcome(unit_name=unit_name, error=str(exc)))

    return DDUploadRunResult(routed=routed, unit_outcomes=outcomes)


def _build_supplemental_records(routed: RoutedFiles, output_root: Path, emit) -> list[Any] | None:
    if not routed.instrument_pdfs:
        return None
    emit("working", f"Reading {len(routed.instrument_pdfs)} supplemental instrument PDF(s)...")
    return build_supplemental_records_from_pdfs(
        routed.instrument_pdfs, output_root / "_supplemental_work", progress_callback=emit
    )


def _run_lite(
    document_paths: list[Path],
    ddr_template_path: Path,
    output_root: Path,
    instructions_text: str,
    emit,
    progress_callback: ProgressCallback | None,
) -> DDUploadRunResult:
    merge_work = output_root / "_merge_work"
    document_paths = merge_multipart_title_opinion_pdfs(document_paths, merge_work)
    routed = route_uploaded_files_without_xref(document_paths, ddr_template_path)

    if not routed.title_opinion_pdfs:
        msg = (
            "No PDFs found in the uploaded files and no Project Log/Xref/Well List "
            "were provided either, so no unit could be identified. Upload the title "
            "opinion PDFs (or ZIPs) in the Documents area."
        )
        emit("err", msg)
        return DDUploadRunResult(routed=routed, fatal_error=msg)

    unit_name = _guess_unit_name(instructions_text, ddr_template_path)
    emit(
        "ok",
        f"{len(routed.title_opinion_pdfs)} title opinion PDF(s) recognized by filename; "
        f"running as unit '{unit_name}'",
    )

    manifest = build_lite_manifest(unit_name, routed.title_opinion_pdfs)
    supplemental_records = _build_supplemental_records(routed, output_root, emit)

    outcomes: list[UnitRunOutcome] = []
    try:
        result = run_dd_pipeline_for_unit(
            unit_name=unit_name,
            ddr_template_path=ddr_template_path,
            output_root=output_root,
            supplemental_records=supplemental_records,
            progress_callback=progress_callback,
            manifest_override=manifest,
        )
        outcomes.append(UnitRunOutcome(unit_name=unit_name, result=result))
    except Exception as exc:
        logger.warning("DD pipeline (lite) failed for unit %s: %s", unit_name, exc)
        emit("err", f"Unit {unit_name} — failed: {exc}")
        outcomes.append(UnitRunOutcome(unit_name=unit_name, error=str(exc)))

    return DDUploadRunResult(routed=routed, unit_outcomes=outcomes)
