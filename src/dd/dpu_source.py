"""Locate, OCR and merge a unit's DPU + Amendment from the project folder.

Bridges dpu_parser (which parses text) to the pipeline (which needs Record
Book/Page per lease). The unit's declaration lives in the client's project
folder, inside the contract's zip:

    <project root>/MAXWELL A UNIT/K1400813 (DECL OF POOLED UNIT ...).zip
        K1400813 (...)/UNIT DEC - REC.TIF            <- the recorded DPU
        K1400813 (...)/UNIT DEC AMENDMENT - REC.TIF  <- the recorded amendment
        K1400813 (...)/UNIT DEC.TIF                  <- unrecorded draft
        K1400813 (...)/CAF.TIF, LEGAL APPROVAL.TIF   <- internal memos

Only the RECORDED instruments ("- REC") are authoritative. The drafts and the
internal approval memos are excluded by name: a known trap in this project is
non-recorded internal material passing a filter and polluting the deliverable.

Client data is read IN PLACE from the project folder and extracted to a working
directory outside the repo; nothing is copied into the repo (invariant 7).
"""
from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.dd.dpu_parser import DPULease, merge_dpu_and_amendments, parse_dpu
from src.utils import get_logger

logger = get_logger(__name__)

# Recorded instruments only. "- REC" marks the county-recorded copy.
_RECORDED_DPU_RE = re.compile(r"UNIT\s*DEC(?!.*AMEND).*-\s*REC\.(TIF|PDF)$", re.IGNORECASE)
_RECORDED_AMENDMENT_RE = re.compile(r"UNIT\s*DEC.*AMEND\w*\s*-\s*REC\.(TIF|PDF)$", re.IGNORECASE)
# Never authoritative: internal approval/routing memos and unrecorded drafts.
_INTERNAL_RE = re.compile(r"\b(CAF|LEGAL\s*APPROVAL|LAR|NOTES)\b", re.IGNORECASE)


@dataclass
class DPUSourceResult:
    leases: list[DPULease] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    dpu_source: str | None = None
    amendment_sources: list[str] = field(default_factory=list)
    recorded_book: str | None = None
    recorded_page: str | None = None

    @property
    def by_lease(self) -> dict[str, DPULease]:
        return {x.lease_no: x for x in self.leases}


def is_internal_document(name: str) -> bool:
    """True for internal memos that must never reach the deliverable."""
    return bool(_INTERNAL_RE.search(Path(name).name))


def extract_unit_contract_zip(zip_path: Path, work_dir: Path) -> Path:
    """Extract a contract zip to a working directory OUTSIDE the repo."""
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(work_dir)
    return work_dir


def find_dpu_documents(folder: Path) -> tuple[Path | None, list[Path]]:
    """(recorded DPU, [recorded amendments]) under *folder*, drafts excluded."""
    dpu: Path | None = None
    amendments: list[Path] = []
    for path in sorted(Path(folder).rglob("*")):
        if not path.is_file() or is_internal_document(path.name):
            continue
        if _RECORDED_AMENDMENT_RE.search(path.name):
            amendments.append(path)
        elif _RECORDED_DPU_RE.search(path.name) and dpu is None:
            dpu = path
    return dpu, amendments


def load_unit_dpu(
    unit_folder: Path | str,
    work_dir: Path | str,
    contract_no: str = "K1400813",
    ocr_fn=None,
) -> DPUSourceResult:
    """Every unit lease's recording reference, from the recorded DPU + Amendment.

    unit_folder: the unit's folder in the project root (read in place).
    work_dir:    a scratch directory OUTSIDE the repo for zip extraction.
    """
    unit_folder = Path(unit_folder)
    work_dir = Path(work_dir)
    result = DPUSourceResult()
    if not unit_folder.exists():
        return result

    source_root = unit_folder
    zips = [p for p in unit_folder.glob(f"{contract_no}*.zip")]
    if zips:
        source_root = extract_unit_contract_zip(sorted(zips)[0], work_dir / contract_no)

    dpu_path, amendment_paths = find_dpu_documents(source_root)
    if dpu_path is None:
        result.notes.append(
            f"No recorded Declaration of Pooled Unit found for {contract_no} under "
            f"{unit_folder.name} — Record Book/Page cannot be populated.")
        return result

    if ocr_fn is None:
        from src.pdf_reader import extract_document

        def ocr_fn(path):  # noqa: E306
            return extract_document(path).full_text or ""

    dpu_doc = parse_dpu(ocr_fn(dpu_path), source=dpu_path.name)
    amendments = [parse_dpu(ocr_fn(p), source=p.name) for p in amendment_paths]
    leases, notes = merge_dpu_and_amendments(dpu_doc, amendments)

    result.leases = leases
    result.notes = notes
    result.dpu_source = dpu_path.name
    result.amendment_sources = [p.name for p in amendment_paths]
    result.recorded_book, result.recorded_page = dpu_doc.recorded_book, dpu_doc.recorded_page
    logger.info("DPU %s: %s leases (%s amendment(s))",
                dpu_path.name, len(leases), len(amendments))
    return result


def reconcile_lease_set(dpu: DPUSourceResult, active_leases: list[str]) -> list[str]:
    """Reconcile the DPU's Exhibit "A" against the unit's ACTIVE lease list.

    The declaration is a historical instrument: it names every lease pooled when
    it was filed (and when its amendment was filed). The current XREF is the
    active work list. A lease in the DPU but not the XREF has since been removed
    from scope by the client — it is NOT a missing lease and must not be added
    back. Recording the difference keeps that decision auditable instead of it
    looking like the pipeline lost leases.
    """
    active = {str(x) for x in active_leases}
    dpu_only = sorted({x.lease_no for x in dpu.leases} - active)
    notes: list[str] = [
        f"Unit lease set reconciled: {len(active)} active lease(s) per the current XREF; "
        f"{len(dpu.leases)} named in {dpu.dpu_source or 'the DPU'}"
        + (f" + {', '.join(dpu.amendment_sources)}" if dpu.amendment_sources else "") + "."
    ]
    if dpu_only:
        notes.append(
            f"{len(dpu_only)} lease(s) appear in the declaration but not the current XREF "
            f"({', '.join(dpu_only)}) — removed from the active work list by the client "
            "(well removals). Correctly excluded from the DDR; not a missing lease.")
    missing = sorted(active - {x.lease_no for x in dpu.leases})
    if missing:
        notes.append(
            f"{len(missing)} active lease(s) are NOT named in the declaration "
            f"({', '.join(missing)}) — no recording reference available from the DPU; verify.")
    return notes


def apply_recording_to_rows(
    rows: list[dict[str, Any]],
    dpu: DPUSourceResult,
    registry=None,
) -> list[str]:
    """Fill Record Book/Page (Ownership cols K/L) on each lease row.

    A lease with no recording in the instrument keeps an EMPTY cell and gets a
    pending reason — the DPU itself prints "Volume__, Page__" for a lease whose
    recording was not yet known, and that blank is the source's, not ours.
    """
    from src.dd.dd_pending import PendingReason

    by_lease = dpu.by_lease
    applied: list[str] = []
    for row in rows:
        entry = by_lease.get(str(row.get("lease_no")))
        if entry is None:
            continue
        row["record_book_source"] = entry.source
        if entry.has_recording:
            row["record_book"] = entry.record_book
            row["record_page"] = entry.record_page
            applied.append(entry.lease_no)
        elif registry is not None:
            registry.add(
                "Ownership Report", f"row {entry.lease_no}", "Record Book/Page",
                PendingReason.PENDING_DOCUMENT,
                f"{entry.source} prints a blank recording reference "
                f"('Volume__, Page__') for this lease — obtain the recorded lease "
                f"or the county reference.",
                identifier=f"lease {entry.lease_no}")
    return applied
