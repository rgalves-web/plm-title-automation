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
import re
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
from src.dd.tabular_source import ColumnSpec, resolve_header_columns, resolve_sheet
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


# Project Log columns, resolved by header — never by position. The positional
# reads this replaces were ALREADY WRONG and nobody noticed: row[6] was assigned
# to aov_percent but column 6 is "Scope of Review", and row[7] to scope_of_review
# but column 7 is "Lease to Well XREF" — so the manifest carried the scope text
# in the AOV field and a column TITLE in the scope field. Silent, plausible, and
# wrong: exactly the failure header resolution exists to prevent.
_PROJECT_LOG_COLUMNS = [
    ColumnSpec("unit_name", ["UNIT NAME"]),
    ColumnSpec("operator", ["OPERATOR"]),
    ColumnSpec("county", ["COUNTY"]),
    ColumnSpec("scope_of_review", ["SCOPE OF REVIEW"]),
    ColumnSpec("aov_percent", ["AOV%", "AOV %", "AOV PERCENT"], required=False),
    ColumnSpec("landman", ["LANDMAN"], required=False),
]


def _load_project_log(manifest: UnitManifest, project_log_path: str | Path) -> None:
    wb = openpyxl.load_workbook(project_log_path, read_only=True, data_only=True)
    ws = wb[PROJECT_LOG_SHEET]

    header = next(ws.iter_rows(min_row=1, max_row=1, values_only=True))
    index = resolve_header_columns(header, _PROJECT_LOG_COLUMNS, source="Project Log")
    unit_col = index["unit_name"]

    def cell(row, field):
        pos = index.get(field)
        return row[pos] if pos is not None and pos < len(row) else None

    matches = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        unit_cell = row[unit_col] if unit_col < len(row) else None
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
    manifest.operator = cell(row, "operator")
    manifest.county = cell(row, "county")
    manifest.aov_percent = cell(row, "aov_percent")
    manifest.scope_of_review = cell(row, "scope_of_review")
    if manifest.operator:
        manifest.seller_name = str(manifest.operator).strip()


_AA_UNIT_LEVEL_NAME = 26  # column AA, present only in older XREF exports
_UNIT_AGREEMENT_TYPE = "UNIT AGREEMENT"


def _unit_leases_via_dpu(wb, unit_name: str, sheets: list[str]) -> set[str]:
    """The unit's leases, derived from its own Declaration of Pooled Unit.

    Newer XREF exports dropped the "UNIT LEVEL NAME" column (AA) that used to
    say which unit a row belonged to. The durable signal is the unit's own DPU:
    it is the UNIT AGREEMENT whose contract NAME carries the unit's distinctive
    token ("DECL OF POOLED UNIT - MAXWELL UNIT A"), and the leases linked to it
    are exactly the unit's leases. Verified against the approved Maxwell
    baseline: this yields its 30 leases exactly.
    """
    from src.dd.agreements_xref import unit_identity_tokens

    identity = unit_identity_tokens(unit_name)
    if not identity:
        return set()
    contracts: set[str] = set()
    for sheet_name in sheets:
        for row in wb[sheet_name].iter_rows(min_row=2, values_only=True):
            if not row or len(row) <= 17 or not row[14]:
                continue
            if str(row[17] or "").strip().upper() != _UNIT_AGREEMENT_TYPE:
                continue
            name_tokens = {t for t in re.split(r"[^A-Z0-9]+", str(row[15] or "").upper()) if t}
            if identity & name_tokens:
                contracts.add(str(row[14]).strip())
    leases: set[str] = set()
    for sheet_name in sheets:
        for row in wb[sheet_name].iter_rows(min_row=2, values_only=True):
            if row and len(row) > 14 and row[1] and str(row[14] or "").strip() in contracts:
                leases.add(str(row[1]).strip())
    return leases


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

    # Does this export still carry the unit-level name column?
    header = next(wb[XREF_SHEET].iter_rows(min_row=1, max_row=1, values_only=True))
    has_unit_column = len(header) > _AA_UNIT_LEVEL_NAME and bool(header[_AA_UNIT_LEVEL_NAME])
    dpu_leases: set[str] = set()
    if not has_unit_column:
        dpu_leases = _unit_leases_via_dpu(wb, manifest.unit_name, sheets_to_read)
        build_log.setdefault("notes", []).append(
            f"XREF export has no 'UNIT LEVEL NAME' column; unit membership derived from the "
            f"unit's own Declaration of Pooled Unit ({len(dpu_leases)} lease(s)).")

    for sheet_name in sheets_to_read:
        ws = wb[sheet_name]
        for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            if has_unit_column:
                aa_raw = row[_AA_UNIT_LEVEL_NAME]
                if not _matches_unit(aa_raw, manifest.unit_name):
                    continue
                exact = _is_exact_single_match(aa_raw, manifest.unit_name)
                tokens = _aa_tokens(aa_raw)
            else:
                if not row or len(row) <= 14 or not row[1]:
                    continue
                if str(row[1]).strip() not in dpu_leases:
                    continue
                # Membership came from the unit's own DPU — an exact statement,
                # not a fuzzy name match on a free-text column.
                aa_raw = manifest.unit_name
                exact = True
                tokens = _aa_tokens(manifest.unit_name)
            record_type3 = str(row[17] or "").strip().upper()
            lease_no = row[1]
            well_or_contract_nb = row[14]

            if record_type3 == _TITLE_OPINION_RECORD_TYPE and well_or_contract_nb:
                entry = to_acc.setdefault(
                    str(well_or_contract_nb),
                    {
                        "lessor": row[2],
                        "lease_no": lease_no,
                        "match_method": row[28] if len(row) > 28 else "dpu_linked",
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


# Well List columns, resolved by header name — never by position. "UNIT NAME"
# moved from index 28 to 23 between exports; a positional read matched no wells
# and silently produced a unit with no represented interest.
_WELL_LIST_COLUMNS = [
    ColumnSpec("unit_name", ["UNIT NAME"]),
    ColumnSpec("well_name", ["WELL NAME"]),
    ColumnSpec("operator", ["OPERATOR"]),
    ColumnSpec("current_wi", ["CURRENT WI"]),
    ColumnSpec("current_nri", ["CURRENT NRI"]),
    ColumnSpec("well_status", ["WELL STATUS"], required=False),
]


def _resolve_wells_sheet(wb, preferred: str):
    """The sheet holding the well rows, by CONTENT not by name.

    Well List exports rename their tabs between versions (the current one has no
    "Wells" sheet — the rows moved to "Sheet1"). "Wells Removed" is never chosen:
    those wells are out of scope and shipping them would re-add removed wells.
    """
    return resolve_sheet(wb, _WELL_LIST_COLUMNS, preferred=preferred,
                         exclude=("removed",), source="Well List")


def _load_well_list(
    manifest: UnitManifest,
    well_list_path: str | Path,
    sheet_name: str = WELLS_SHEET,
) -> None:
    wb = openpyxl.load_workbook(well_list_path, read_only=True, data_only=True)
    ws = _resolve_wells_sheet(wb, sheet_name)

    # Resolve columns by HEADER, not position: exports move them. "UNIT NAME"
    # sat at column AC (28) in the previous export and at 23 in the current one,
    # so a positional read silently matched no wells at all — which left the
    # unit with no represented interest and a zero gross-acre denominator.
    header = next(ws.iter_rows(min_row=1, max_row=1, values_only=True))
    index = resolve_header_columns(header, _WELL_LIST_COLUMNS, source=f"Well List:{ws.title}")
    unit_col = index["unit_name"]

    def cell(row, field):
        pos = index.get(field)
        return row[pos] if pos is not None and pos < len(row) else None

    matches = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        unit_cell = row[unit_col] if unit_col < len(row) else None
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
                well_name=str(cell(row, "well_name")),
                well_operator=cell(row, "operator"),
                well_api=None,  # not carried by Well List; cross-ref XREF if ever needed
                well_prod_status=cell(row, "well_status"),
                current_wi=str(cell(row, "current_wi")),
                current_nri=str(cell(row, "current_nri")),
                unit_name_raw=cell(row, "unit_name"),
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
