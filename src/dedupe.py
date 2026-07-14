from __future__ import annotations

from difflib import SequenceMatcher

try:
    from rapidfuzz import fuzz
except Exception:  # pragma: no cover - fallback only used without rapidfuzz
    fuzz = None

from src.schemas import SourceDocument
from src.utils import clean_cell, normalize_text


def deduplicate_documents(
    records: list[SourceDocument],
    fuzzy_threshold: float = 92.0,
) -> list[SourceDocument]:
    seen_instruments: dict[str, SourceDocument] = {}
    canonical_records: list[SourceDocument] = []

    for record in records:
        instrument_key = _instrument_key(record)
        if instrument_key and instrument_key in seen_instruments:
            canonical = seen_instruments[instrument_key]
            record.duplicate_of = canonical.source_document_id
            record.dedupe_confidence = 1.0
            continue

        fuzzy_match = _find_fuzzy_duplicate(record, canonical_records, fuzzy_threshold)
        if fuzzy_match:
            canonical, score = fuzzy_match
            record.duplicate_of = canonical.source_document_id
            record.dedupe_confidence = round(score / 100, 3)
            continue

        canonical_records.append(record)
        if instrument_key:
            seen_instruments[instrument_key] = record

    return records


def _instrument_key(record: SourceDocument) -> str | None:
    instrument = clean_cell(record.instrument_number)
    if instrument:
        return f"inst:{normalize_text(instrument)}"
    book = clean_cell(record.book)
    page = clean_cell(record.page)
    if book and page:
        return f"book-page:{normalize_text(book)}:{normalize_text(page)}"
    return None


def _find_fuzzy_duplicate(
    record: SourceDocument,
    candidates: list[SourceDocument],
    threshold: float,
) -> tuple[SourceDocument, float] | None:
    record_key = _fuzzy_text(record)
    if not record_key:
        return None

    best_candidate: SourceDocument | None = None
    best_score = 0.0
    for candidate in candidates:
        if not _dates_compatible(record, candidate):
            continue
        candidate_key = _fuzzy_text(candidate)
        if not candidate_key:
            continue
        score = _ratio(record_key, candidate_key)
        if score > best_score:
            best_candidate = candidate
            best_score = score

    if best_candidate and best_score >= threshold:
        return best_candidate, best_score
    return None


def _fuzzy_text(record: SourceDocument) -> str:
    return normalize_text(
        " ".join(
            value
            for value in [
                record.document_type,
                record.document_title,
                record.grantor,
                record.grantee,
                record.legal_description,
            ]
            if value
        )
    )


def _dates_compatible(left: SourceDocument, right: SourceDocument) -> bool:
    if left.recording_date and right.recording_date:
        return left.recording_date == right.recording_date
    if left.instrument_date and right.instrument_date:
        return left.instrument_date == right.instrument_date
    return True


def _ratio(left: str, right: str) -> float:
    if fuzz:
        return float(fuzz.token_sort_ratio(left, right))
    return SequenceMatcher(None, left, right).ratio() * 100
