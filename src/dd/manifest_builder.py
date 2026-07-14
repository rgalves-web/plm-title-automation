"""Build a UnitManifest from the 3 client reference workbooks.

Project Log uses a single UNIT NAME value per row (exact match). Lease to Well
XREF's UNIT LEVEL NAME (column AA) is semicolon-delimited when a lease/contract
spans multiple units — matching must accept an exact whole-cell match OR
membership as one semicolon-separated token. Well List's UNIT NAME column is
also single-valued (exact match).

confirm_coverage on a TitleOpinionRef is True unless at least one XREF row
contributing to that title opinion had an AA value that was an *exact*,
non-ambiguous single-unit match — i.e. False only when there is a genuine,
unambiguous link between the title opinion and the unit. This is intentional:
title opinions whose only link is "this lease's AA cell happens to also list
five other unit names" need human confirmation before being trusted.
"""
from __future__ import annotations

import glob
import json
import zipfile
from pathlib import Path
from typing import Any

import openpyxl
import yaml

from src.dd.manifest import (
    LeaseRef,
    ReferenceContractRef,
    RepresentedInterest,
    TitleOpinionRef,
    UnitManifest,
    WellRef,
)
from src.utils import get_logger, parse_date, timestamp

logger = get_logger(__name__)

PROJECT_LOG_SHEET = "Project Log"
XREF_SHEET = "Sheet1"
XREF_SHEET2 = "Sheet2"
WELLS_SHEET = "Wells"
WELLS_PRELIM_SHEET = "Wells - Prelim AV%"

_CONTRACT_RECORD_TYPES = {
    "FARMOUT AGREEMENT",
    "ASSIGNMENT",
    "UNIT AGREEMENT",
    "PURCHASE-SALE",
    "BILL OF SALE",
}
_TITLE_OPINION_RECORD_TYPE = "TITLE OPINIONS"


class ManifestBuildError(RuntimeError):
    pass


def _aa_tokens(aa_raw: Any) -> list[str]:
    if not aa_raw:
        return []
    return [tok.strip() for tok in str(aa_raw).split(";") if tok.strip()]


def _matches_unit(aa_raw: Any, unit_name: str) -> bool:
    if not aa_raw:
        return False
    target = unit_name.casefold()
    if str(aa_raw).strip().casefold() == target:
        return True
    return any(tok.casefold() == target for tok in _aa_tokens(aa_raw))


def _is_exact_single_match(aa_raw: Any, unit_name: str) -> bool:
    if not aa_raw:
        return False
    return str(aa_raw).strip().casefold() == unit_name.casefold()


def _confirm_coverage(any_exact_match_seen: bool) -> bool:
    return not any_exact_match_seen


def build_manifest(
    unit_name: str,
    project_log_path: str | Path,
    xref_path: str | Path,
    well_list_path: str | Path | None = None,
    to_files_dir: str | Path | None = None,
) -> UnitManifest:
    """Build a UnitManifest.

    When *well_list_path* is None the well data is read from the
    ``Wells - Prelim AV%`` sheet embedded in the Project Log workbook.
    """
    manifest = UnitManifest(unit_name=unit_name)
    manifest.generated_at = timestamp()
    manifest.source_workbooks = {
        "project_log": str(project_log_path),
        "xref": str(xref_path),
        "well_list": str(well_list_path) if well_list_path is not None else str(project_log_path),
    }

    build_log: dict[str, Any] = {
        "unit_name": unit_name,
        "title_opinion_rows": {},
        "reference_contract_rows": {},
        "lease_rows": {},
    }

    _load_project_log(manifest, project_log_path)
    _load_xref(manifest, xref_path, build_log)
    if to_files_dir is not None:
        _probe_pdf_availability(manifest, to_files_dir)

    if well_list_path is None:
        _load_well_list(manifest, project_log_path, sheet_name=WELLS_PRELIM_SHEET)
    else:
        _load_well_list(manifest, well_list_path, sheet_name=WELLS_SHEET)

    return manifest, build_log


def _load_project_log(manifest: UnitManifest, project_log_path: str | Path) -> None:
    wb = openpyxl.load_workbook(project_log_path, read_only=True, data_only=True)
    ws = wb[PROJECT_LOG_SHEET]

    matches = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        unit_cell = row[4]  # column E
        if unit_cell and str(unit_cell).strip().casefold() == manifest.unit_name.casefold():
            matches.append(row)
    wb.close()

    if not matches:
        raise ManifestBuildError(
            f"Unit '{manifest.unit_name}' not found in Project Log (column E)."
        )
    if len(matches) > 1:
        raise ManifestBuildError(
            f"Unit '{manifest.unit_name}' matched {len(matches)} rows in Project Log "
            "(column E) — ambiguous, expected exactly 1."
        )

    row = matches[0]
    manifest.operator = row[1]  # column B
    manifest.county = row[2]  # column C
    manifest.aov_percent = row[6]  # column G
    manifest.scope_of_review = row[7]  # column H
    if manifest.operator:
        manifest.seller_name = str(manifest.operator).strip()


def _load_xref(
    manifest: UnitManifest,
    xref_path: str | Path,
    build_log: dict[str, Any],
) -> None:
    wb = openpyxl.load_workbook(xref_path, read_only=True, data_only=True)

    to_acc: dict[str, dict[str, Any]] = {}
    contract_acc: dict[str, dict[str, Any]] = {}
    lease_acc: dict[str, dict[str, Any]] = {}

    sheets_to_read = [XREF_SHEET]
    if XREF_SHEET2 in wb.sheetnames:
        sheets_to_read.append(XREF_SHEET2)

    for sheet_name in sheets_to_read:
        ws = wb[sheet_name]
        for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            aa_raw = row[26]  # column AA
            if not _matches_unit(aa_raw, manifest.unit_name):
                continue

            exact = _is_exact_single_match(aa_raw, manifest.unit_name)
            tokens = _aa_tokens(aa_raw)
            record_type3 = str(row[17] or "").strip().upper()
            lease_no = row[1]
            well_or_contract_nb = row[14]

            if record_type3 == _TITLE_OPINION_RECORD_TYPE and well_or_contract_nb:
                entry = to_acc.setdefault(
                    str(well_or_contract_nb),
                    {
                        "lessor": row[2],
                        "lease_no": lease_no,
                        "match_method": row[28],
                        "tokens": set(),
                        "exact_match_seen": False,
                        "source_rows": [],
                    },
                )
                entry["tokens"].update(tokens)
                entry["exact_match_seen"] = entry["exact_match_seen"] or exact
                entry["source_rows"].append(row_num)

            elif record_type3 in _CONTRACT_RECORD_TYPES and well_or_contract_nb:
                entry = contract_acc.setdefault(
                    str(well_or_contract_nb),
                    {
                        "record_type": record_type3,
                        "lessor": row[2],
                        "lessee": row[3],
                        "lease_no": lease_no,
                        "tokens": set(),
                        "source_rows": [],
                    },
                )
                entry["tokens"].update(tokens)
                entry["source_rows"].append(row_num)

            if lease_no:
                entry = lease_acc.setdefault(
                    str(lease_no),
                    {
                        "lessor": row[2],
                        "lessee": row[3],
                        "lease_date": row[8],
                        "eff_date": row[9],
                        "exp_date": row[10],
                        "ext_exp_date": row[11],
                        "property_status": row[7],
                        "rights_held": row[6],
                        "state": row[12],
                        "county": row[13],
                        "tokens": set(),
                        "source_rows": [],
                    },
                )
                entry["tokens"].update(tokens)
                entry["source_rows"].append(row_num)

    wb.close()

    for file_number, entry in sorted(to_acc.items()):
        manifest.title_opinions.append(
            TitleOpinionRef(
                file_number=file_number,
                lessor=entry["lessor"],
                lease_no=entry["lease_no"],
                match_method=entry["match_method"],
                matched_unit_tokens=sorted(entry["tokens"]),
                confirm_coverage=_confirm_coverage(entry["exact_match_seen"]),
                source_rows=entry["source_rows"],
            )
        )
        build_log["title_opinion_rows"][file_number] = entry["source_rows"]

    for file_number, entry in sorted(contract_acc.items()):
        manifest.reference_contracts.append(
            ReferenceContractRef(
                file_number=file_number,
                record_type=entry["record_type"],
                lessor=entry["lessor"],
                lessee=entry["lessee"],
                lease_no=entry["lease_no"],
                matched_unit_tokens=sorted(entry["tokens"]),
                source_rows=entry["source_rows"],
            )
        )
        build_log["reference_contract_rows"][file_number] = entry["source_rows"]

    for lease_no, entry in sorted(lease_acc.items()):
        manifest.leases.append(
            LeaseRef(
                lease_no=lease_no,
                lessor=entry["lessor"],
                lessee=entry["lessee"],
                lease_date=parse_date(entry["lease_date"]),
                eff_date=parse_date(entry["eff_date"]),
                exp_date=parse_date(entry["exp_date"]),
                ext_exp_date=parse_date(entry["ext_exp_date"]),
                property_status=entry["property_status"],
                rights_held=entry["rights_held"],
                state=entry["state"],
                county=entry["county"],
                matched_unit_tokens=sorted(entry["tokens"]),
                source_rows=entry["source_rows"],
            )
        )
        build_log["lease_rows"][lease_no] = entry["source_rows"]

    if not to_acc:
        logger.warning(
            "No TITLE OPINIONS found in XREF for unit '%s'.", manifest.unit_name
        )


def _probe_pdf_availability(manifest: UnitManifest, to_files_dir: str | Path) -> None:
    to_files_dir = Path(to_files_dir)
    if not to_files_dir.exists():
        logger.warning("to_files_dir does not exist: %s", to_files_dir)
        return

    for to_ref in manifest.title_opinions:
        matches = sorted(glob.glob(str(to_files_dir / f"{to_ref.file_number}*")))
        pdf_path = None
        for match in matches:
            match_path = Path(match)
            if match_path.is_file() and match_path.suffix.lower() == ".pdf":
                pdf_path = match_path
                break
            if match_path.suffix.lower() == ".zip":
                try:
                    with zipfile.ZipFile(match_path) as zf:
                        pdf_members = [
                            info
                            for info in zf.infolist()
                            if not info.is_dir()
                            and info.file_size > 0
                            and info.filename.lower().endswith(".pdf")
                        ]
                except zipfile.BadZipFile:
                    continue
                if pdf_members:
                    pdf_path = match_path
                    break
        to_ref.pdf_available = pdf_path is not None
        to_ref.pdf_path = str(pdf_path) if pdf_path else None


def set_title_opinions_from_uploads(
    manifest: UnitManifest,
    pdf_paths: list[str | Path],
) -> None:
    """Bind explicitly-uploaded title-opinion PDFs to a single-unit manifest.

    The client's TO PDFs are named descriptively ("T-O ORIG BOWEN A-1449...")
    and carry no xref file number, so glob-based probing in
    _probe_pdf_availability can never find them. When the analyst selects one
    unit and hands us exactly that unit's TO PDFs, those PDFs *are* the title
    opinions to parse — provenance confirms coverage. This replaces the
    xref-derived TitleOpinionRef list (which would otherwise show 9 file
    numbers with no PDF) with one confirm_coverage=True ref per uploaded PDF,
    preserving any xref file-number match in the ref's file_number label.

    Leases / wells / represented_interest / seller stay untouched — only the
    title_opinions list is replaced.
    """
    import re

    refs: list[TitleOpinionRef] = []
    xref_numbers = [to.file_number for to in manifest.title_opinions]

    for path in sorted(pdf_paths, key=lambda p: str(p)):
        path = Path(path)
        stem = path.stem
        matched = next((n for n in xref_numbers if n and stem.upper().startswith(n.upper())), None)
        file_number = matched or re.sub(r"[^A-Za-z0-9\-]", "_", stem)[:60]
        refs.append(
            TitleOpinionRef(
                file_number=file_number,
                match_method="uploaded_for_unit",
                confirm_coverage=True,
                pdf_available=True,
                pdf_path=str(path),
            )
        )

    if refs:
        manifest.title_opinions = refs


def _load_well_list(
    manifest: UnitManifest,
    well_list_path: str | Path,
    sheet_name: str = WELLS_SHEET,
) -> None:
    wb = openpyxl.load_workbook(well_list_path, read_only=True, data_only=True)
    ws = wb[sheet_name]

    matches = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        unit_cell = row[28]  # column AC
        if unit_cell and str(unit_cell).strip().casefold() == manifest.unit_name.casefold():
            matches.append(row)
    wb.close()

    if not matches:
        logger.warning(
            "No wells found in Well List for unit '%s'.", manifest.unit_name
        )
        return

    for row in matches:
        manifest.wells.append(
            WellRef(
                well_name=str(row[2]),  # column C
                well_operator=row[0],  # column A
                well_api=None,  # not carried by Well List; cross-ref XREF if ever needed
                well_prod_status=row[29],  # column AD (WELL STATUS)
                current_wi=str(row[5]),  # column F
                current_nri=str(row[6]),  # column G
                unit_name_raw=row[28],
            )
        )

    wi_values = {w.current_wi for w in manifest.wells}
    nri_values = {w.current_nri for w in manifest.wells}
    if len(wi_values) > 1 or len(nri_values) > 1:
        manifest.manifest_notes.append(
            f"Wells disagree on CURRENT WI/NRI: WI={wi_values} NRI={nri_values}. "
            "Using first well's values as represented_interest."
        )

    first = manifest.wells[0]
    manifest.represented_interest = RepresentedInterest(
        current_wi=first.current_wi,
        current_nri=first.current_nri,
        as_of_well_names=[w.well_name for w in manifest.wells],
    )


def write_manifest(
    manifest: UnitManifest,
    build_log: dict[str, Any],
    output_dir: str | Path,
) -> tuple[Path, Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = output_dir / "manifest.yaml"
    with manifest_path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(
            manifest.model_dump(mode="json"),
            handle,
            sort_keys=False,
            default_flow_style=False,
        )

    build_log_path = output_dir / "manifest_build_log.json"
    with build_log_path.open("w", encoding="utf-8") as handle:
        json.dump(build_log, handle, indent=2, default=str)

    return manifest_path, build_log_path


def build_and_write_manifest(
    unit_name: str,
    project_log_path: str | Path,
    xref_path: str | Path,
    well_list_path: str | Path | None = None,
    output_root: str | Path = "data/input/dd",
    to_files_dir: str | Path | None = None,
) -> tuple[UnitManifest, Path, Path]:
    manifest, build_log = build_manifest(
        unit_name, project_log_path, xref_path, well_list_path, to_files_dir
    )
    output_dir = Path(output_root) / unit_name
    manifest_path, build_log_path = write_manifest(manifest, build_log, output_dir)
    return manifest, manifest_path, build_log_path
