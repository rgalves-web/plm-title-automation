from __future__ import annotations

import re
from datetime import date

from src.schemas import LeaseStatus, SourceDocument
from src.utils import normalize_text


def is_oil_and_gas_lease(record: SourceDocument) -> bool:
    text = normalize_text(record.search_text())
    return (
        "oil and gas lease" in text
        or "oil & gas lease" in text
        or "o&g lease" in text
        or "oil gas lease" in text
    )


def infer_lease_status(
    record: SourceDocument,
    extracted_text: str | None = None,
    today: date | None = None,
) -> LeaseStatus | None:
    if not is_oil_and_gas_lease(record):
        return None

    today = today or date.today()
    text = normalize_text(f"{record.search_text()} {extracted_text or ''}")

    if "release of oil and gas lease" in text or "release of o&g lease" in text:
        return LeaseStatus.RELEASED
    if any(term in text for term in ("released", "terminated")):
        return LeaseStatus.RELEASED
    if any(term in text for term in ("expired", "expiration", "primary term expired")):
        return LeaseStatus.EXPIRED
    if any(term in text for term in ("held by production", " hbp ", "active", "extended")):
        return LeaseStatus.ACTIVE

    years = _parse_primary_term_years(text)
    base_date = record.instrument_date or record.recording_date
    if years and base_date:
        estimated_expiration = _add_years(base_date, years)
        return LeaseStatus.EXPIRED if estimated_expiration < today else LeaseStatus.ACTIVE

    return LeaseStatus.REVIEW


def _parse_primary_term_years(text: str) -> int | None:
    match = re.search(r"primary term (?:of )?(\d{1,2}) years?", text)
    if match:
        return int(match.group(1))
    match = re.search(r"(\d{1,2}) year primary term", text)
    if match:
        return int(match.group(1))
    return None


def _add_years(value: date, years: int) -> date:
    try:
        return value.replace(year=value.year + years)
    except ValueError:
        return value.replace(month=2, day=28, year=value.year + years)
