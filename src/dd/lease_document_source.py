"""Per-lease detail from individual recorded lease documents (Collin closing).

Some unit leases have their own recorded instrument in the client's "NEW FILES"
tree (a folder named by lease number, e.g. "0190122-005 (…)/…/LEASE.pdf"), which
is the AUTHORITATIVE source for that lease's terms — royalty, dates, recording,
clauses — where the title-opinion lease schedule is silent. This module locates
each lease's document and extracts it via the existing LLM-first lease_parser
(cached), returning per-lease fields for the pipeline to merge. It never decides
conflicts: the merge layer itemizes any TO-vs-document disagreement for review.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from src.dd.lease_parser import parse_lease
from src.utils import get_logger

logger = get_logger(__name__)

# LeaseExtraction field -> the lease-row key the DDR writer consumes.
_FIELD_MAP = {
    "royalty": "royalty_text",
    "lease_date": "effective_date",
    "recording_info": "recording_info",
    "primary_term": "primary_term",
    "shut_in_royalty": "shut_in_royalty",
    "pooling_clause": "pooling",
    "horizontal_pugh": "horizontal_pugh",
    "vertical_pugh": "vertical_pugh",
    "depth_limitations": "depth_limitations",
    "legal_description": "legal_description",
}


def find_lease_document(lease_document_dir: Path, lease_no: str) -> Path | None:
    """The LEASE instrument for *lease_no* (prefer a .pdf over a .tif); the
    lease's own folder is named starting with its number."""
    matches: list[Path] = []
    for pattern in (f"{lease_no}*/**/LEASE.pdf", f"{lease_no}*/**/LEASE.PDF",
                    f"{lease_no}*/**/LEASE.tif", f"{lease_no}*/**/LEASE.TIF"):
        matches.extend(lease_document_dir.glob(pattern))
        if matches:
            break
    return sorted(matches)[0] if matches else None


def build_lease_document_details(
    lease_document_dir: str | Path,
    leases: list[Any],
    work_dir: str | Path,
    cache_dir: str | Path | None = None,
    progress=None,
) -> dict[str, dict[str, Any]]:
    """lease_no -> {row_key: value, ..., "_source": path, "_confidence": {...}}
    for every unit lease that has a recorded lease document on disk."""
    lease_document_dir = Path(lease_document_dir)
    if not lease_document_dir.exists():
        return {}

    out: dict[str, dict[str, Any]] = {}
    for lease in leases:
        lease_no = str(getattr(lease, "lease_no", "") or "")
        if not lease_no:
            continue
        doc = find_lease_document(lease_document_dir, lease_no)
        if doc is None:
            continue
        if progress:
            progress("working", f"Lease {lease_no} — reading lease document {doc.name}")
        ext = parse_lease(doc, lease_key=lease_no, work_dir=work_dir, cache_dir=cache_dir)
        if ext.error:
            logger.warning("Lease document parse failed for %s: %s", lease_no, ext.error)
            continue
        fields: dict[str, Any] = {"_source": f"{doc.name} (lease document)", "_confidence": {}}
        for attr, row_key in _FIELD_MAP.items():
            field = getattr(ext, attr, None)
            if field and field.value:
                fields[row_key] = field.value
                fields["_confidence"][row_key] = field.confidence
        out[lease_no] = fields
    return out
