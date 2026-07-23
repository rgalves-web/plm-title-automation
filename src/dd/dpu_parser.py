"""Declaration of Pooled Unit + its Amendment as a first-class source
(Maxwell lessons item 3).

The DPU's Exhibit "A" is the authoritative list of the leases pooled into a unit,
and it carries each lease's recording reference (Volume/Page) — the Record
Book/Page columns of the Ownership Report. An AMENDMENT of the DPU is equally
authoritative and additive: EOG amends a declaration when leases "were
inadvertently excluded from Exhibit A", so reading only the original DPU yields
a unit that is missing leases and a workbook that silently understates it.

Exhibit A entries are rigidly structured, so this is deterministic regex parsing
with no LLM in the loop:

    EOG Lease Number: 190122-001
    Lease Date: August 23, 2006
    Lessor: Joan B. Maxwell
    Original Lessee: EOG Resources, Inc.
    Recording Information: Volume 402, Page 50, Montague County, Texas

The recording reference is printed both as "Volume 402, Page 50" (original) and
"Vol. 571, Pg. 82" (amendment); both forms are read. Lease numbers print without
their leading zero in the instrument ("190122-001") but carry it everywhere else
("0190122-001"), so they are normalized to the canonical form.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# One Exhibit A entry. Fields are captured verbatim; only the lease number is
# normalized (to the canonical zero-padded form used by the manifest and XREF).
_ENTRY_SPLIT_RE = re.compile(r"EOG\s+Lease\s+Number\s*:", re.IGNORECASE)
_FIELD_RES = {
    "lease_date": re.compile(r"Lease\s+Date\s*:\s*(.+)", re.IGNORECASE),
    "lessor": re.compile(r"Lessor\s*:\s*(.+?)(?=\n\s*Original\s+Lessee\s*:)", re.IGNORECASE | re.DOTALL),
    "original_lessee": re.compile(r"Original\s+Lessee\s*:\s*(.+)", re.IGNORECASE),
    "recording_text": re.compile(r"Recording\s+Information\s*:\s*(.+)", re.IGNORECASE),
}
# "Volume 402, Page 50" | "Vol. 571, Pg. 82" | "Book 491, at Page 160"
_VOL_PAGE_RE = re.compile(
    r"\b(?:Vol(?:ume)?|Book)\.?\s*(\d{1,5})\s*,?\s*(?:at\s+)?(?:P(?:a)?g(?:e)?)\.?\s*(\d{1,5})\b",
    re.IGNORECASE,
)
_LEASE_NO_RE = re.compile(r"\b(\d{6,7})\s*-\s*(\d{3})\b")


def normalize_lease_no(text: str | None) -> str | None:
    """"190122-001" -> "0190122-001"; already-canonical values pass through."""
    if not text:
        return None
    match = _LEASE_NO_RE.search(str(text))
    if not match:
        return None
    return f"{match.group(1).zfill(7)}-{match.group(2)}"


@dataclass
class DPULease:
    lease_no: str
    lease_date: str | None = None
    lessor: str | None = None
    original_lessee: str | None = None
    recording_text: str | None = None
    record_book: str | None = None   # Ownership Report col K
    record_page: str | None = None   # Ownership Report col L
    source: str = ""                 # which instrument this entry came from

    @property
    def has_recording(self) -> bool:
        return bool(self.record_book and self.record_page)


@dataclass
class DPUDocument:
    unit_name: str | None = None
    effective_date: str | None = None
    recorded_book: str | None = None   # where the DPU itself is recorded
    recorded_page: str | None = None
    leases: list[DPULease] = None      # type: ignore[assignment]
    is_amendment: bool = False

    def __post_init__(self) -> None:
        if self.leases is None:
            self.leases = []


def _clean(text: str | None) -> str | None:
    if text is None:
        return None
    collapsed = re.sub(r"\s+", " ", str(text)).strip()
    return collapsed or None


def parse_vol_page(text: str | None) -> tuple[str | None, str | None]:
    """("Volume 402, Page 50, Montague County, Texas") -> ("402", "50")."""
    if not text:
        return None, None
    match = _VOL_PAGE_RE.search(str(text))
    return (match.group(1), match.group(2)) if match else (None, None)


def parse_exhibit_a(text: str, source: str = "") -> list[DPULease]:
    """Every "EOG Lease Number:" entry in an Exhibit A (or amendment) body."""
    leases: list[DPULease] = []
    chunks = _ENTRY_SPLIT_RE.split(text)[1:]  # drop the preamble before entry 1
    for chunk in chunks:
        lease_no = normalize_lease_no(chunk.split("\n", 1)[0])
        if not lease_no:
            continue
        entry = DPULease(lease_no=lease_no, source=source)
        for field, pattern in _FIELD_RES.items():
            match = pattern.search(chunk)
            if match:
                setattr(entry, field, _clean(match.group(1)))
        entry.record_book, entry.record_page = parse_vol_page(entry.recording_text)
        leases.append(entry)
    return leases


def parse_dpu(text: str, source: str = "") -> DPUDocument:
    """Parse a Declaration of Pooled Unit or an Amendment of one."""
    is_amendment = bool(re.search(r"AMENDMENT\s+OF\s+DECLARATION\s+OF\s+POOLED\s+UNIT",
                                  text, re.IGNORECASE))
    # OCR routinely mangles the dash between the title and the unit name
    # ("POOLED UNIT �- MAXWELL A UNIT"), so accept any short run of
    # non-alphanumeric characters as the separator rather than a fixed dash.
    unit_match = re.search(
        r"DECLARATION\s+OF\s+POOLED\s+UNIT\s*[^A-Za-z0-9\n]{0,6}\s*([A-Z][A-Z0-9 .\'&]*?)\s*(?:\n|STATE\b|$)",
        text, re.IGNORECASE)
    effective = re.search(r"effective\s+(?:as\s+of\s+)?([A-Z][a-z]+\s+\d{1,2},\s*\d{4})",
                          text, re.IGNORECASE)
    # The instrument's own recording stamp is the FIRST Vol/Page on the page.
    book, page = parse_vol_page(text[:400])
    return DPUDocument(
        unit_name=_clean(unit_match.group(1)) if unit_match else None,
        effective_date=_clean(effective.group(1)) if effective else None,
        recorded_book=book,
        recorded_page=page,
        leases=parse_exhibit_a(text, source=source),
        is_amendment=is_amendment,
    )


def merge_dpu_and_amendments(
    dpu: DPUDocument,
    amendments: list[DPUDocument],
) -> tuple[list[DPULease], list[str]]:
    """The unit's full lease set: the DPU's Exhibit A plus every lease an
    amendment adds. Returns (leases, notes).

    An amendment ADDS leases that were inadvertently excluded; when it restates a
    lease already in Exhibit A, the amendment is the later instrument and wins,
    and the change is noted rather than applied silently.
    """
    by_lease: dict[str, DPULease] = {lease.lease_no: lease for lease in dpu.leases}
    notes: list[str] = []
    for amendment in amendments:
        for lease in amendment.leases:
            existing = by_lease.get(lease.lease_no)
            if existing is None:
                by_lease[lease.lease_no] = lease
                notes.append(
                    f"{lease.lease_no}: added to the unit by {lease.source or 'the amendment'} "
                    f"(inadvertently excluded from the original Exhibit A); recording "
                    f"Vol. {lease.record_book}, Pg. {lease.record_page}.")
            elif (existing.record_book, existing.record_page) != (lease.record_book, lease.record_page):
                notes.append(
                    f"{lease.lease_no}: amendment restates recording as Vol. {lease.record_book}, "
                    f"Pg. {lease.record_page} (Exhibit A had Vol. {existing.record_book}, "
                    f"Pg. {existing.record_page}) — using the amendment; verify.")
                by_lease[lease.lease_no] = lease
    return [by_lease[k] for k in sorted(by_lease)], notes
