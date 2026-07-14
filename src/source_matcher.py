from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from zipfile import ZipFile

from rapidfuzz import fuzz, process

from src.intake import _document_number_key
from src.lease_engine import is_oil_and_gas_lease
from src.schemas import ClassificationStatus, QAException, SourceDocument
from src.utils import clean_cell, normalize_text, safe_filename


SOURCE_FILE_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}


@dataclass(frozen=True)
class SourceFileCandidate:
    display_name: str
    file_name: str
    normalized_file_name: str
    normalized_display_name: str
    document_number_key: str
    archive_path: Path | None = None
    member_name: str | None = None
    path: Path | None = None


def requires_source_reading(record: SourceDocument) -> bool:
    if record.status in {ClassificationStatus.REDLINE, ClassificationStatus.DUPLICATE}:
        return False
    return (
        record.status
        in {
            ClassificationStatus.INCLUDE_FULL,
            ClassificationStatus.INCLUDE_LIMITED,
            ClassificationStatus.REVIEW,
        }
        or is_oil_and_gas_lease(record)
    )


def match_source_files(
    records: list[SourceDocument],
    document_package_path: str | Path | None = None,
    extracted_document_folder: str | Path | None = None,
) -> list[QAException]:
    candidates = build_source_file_candidates(
        document_package_path=document_package_path,
        extracted_document_folder=extracted_document_folder,
    )
    exceptions: list[QAException] = []
    if not candidates:
        return exceptions

    for record in records:
        candidate, method, confidence = _best_match(record, candidates)
        if candidate:
            _apply_source_match(record, candidate, method, confidence)
        else:
            _clear_source_match(record)
            if requires_source_reading(record):
                exceptions.append(
                    QAException(
                        severity="ERROR",
                        code="SOURCE_FILE_NOT_MATCHED",
                        message="Required source document was not matched to a package file.",
                        source_document_id=record.source_document_id,
                        field="matched_source_file",
                    )
                )
    return exceptions


def build_source_file_candidates(
    document_package_path: str | Path | None = None,
    extracted_document_folder: str | Path | None = None,
) -> list[SourceFileCandidate]:
    if document_package_path:
        return _zip_candidates(Path(document_package_path))
    if extracted_document_folder:
        return _folder_candidates(Path(extracted_document_folder))
    return []


def materialize_matched_source_file(
    record: SourceDocument,
    output_dir: str | Path,
) -> Path | None:
    matched_path = record.source_trace.get("matched_source_path")
    if matched_path:
        path = Path(matched_path)
        return path if path.exists() else None

    archive_path = record.source_trace.get("source_package_path")
    member_name = record.source_trace.get("matched_source_member")
    if not archive_path or not member_name:
        return None

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / _materialized_file_name(record, member_name)
    if output_path.exists():
        return output_path

    with ZipFile(archive_path) as archive:
        with archive.open(member_name) as source, output_path.open("wb") as target:
            while True:
                chunk = source.read(1024 * 1024 * 4)
                if not chunk:
                    break
                target.write(chunk)
    return output_path


def _zip_candidates(zip_path: Path) -> list[SourceFileCandidate]:
    candidates: list[SourceFileCandidate] = []
    if not zip_path.exists():
        return candidates
    with ZipFile(zip_path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            suffix = Path(info.filename).suffix.lower()
            if suffix not in SOURCE_FILE_SUFFIXES:
                continue
            candidates.append(
                _candidate(
                    display_name=info.filename,
                    archive_path=zip_path,
                    member_name=info.filename,
                )
            )
    return candidates


def _folder_candidates(folder: Path) -> list[SourceFileCandidate]:
    candidates: list[SourceFileCandidate] = []
    if not folder.exists():
        return candidates
    for path in folder.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in SOURCE_FILE_SUFFIXES:
            continue
        candidates.append(_candidate(display_name=str(path), path=path))
    return candidates


def _candidate(
    display_name: str,
    archive_path: Path | None = None,
    member_name: str | None = None,
    path: Path | None = None,
) -> SourceFileCandidate:
    file_name = Path(display_name).name
    return SourceFileCandidate(
        display_name=display_name,
        file_name=file_name,
        normalized_file_name=_normalize_filename(file_name),
        normalized_display_name=_normalize_filename(display_name),
        document_number_key=_document_number_key(Path(file_name).stem),
        archive_path=archive_path,
        member_name=member_name,
        path=path.resolve() if path else None,
    )


def _best_match(
    record: SourceDocument,
    candidates: list[SourceFileCandidate],
) -> tuple[SourceFileCandidate | None, str | None, float | None]:
    original = clean_cell(record.original_file_name)
    if original:
        original_file = _normalize_filename(Path(original).name)
        original_display = _normalize_filename(original)
        for candidate in candidates:
            if candidate.normalized_file_name == original_file:
                return candidate, "original_file_name", 1.0
            if candidate.normalized_display_name == original_display:
                return candidate, "original_file_name", 1.0

    instrument_key = _document_number_key(record.instrument_number)
    if instrument_key:
        for candidate in candidates:
            if candidate.document_number_key == instrument_key:
                return candidate, "instrument_number", 0.95

    book_page_match = _match_by_book_page(record, candidates)
    if book_page_match:
        return book_page_match, "book_page", 0.80

    fuzzy_match = _match_by_fuzzy_name(record, candidates)
    if fuzzy_match:
        return fuzzy_match

    return None, None, None


def _match_by_book_page(
    record: SourceDocument,
    candidates: list[SourceFileCandidate],
) -> SourceFileCandidate | None:
    book_key = _document_number_key(record.book)
    page_key = _document_number_key(record.page)
    if not book_key or not page_key:
        return None
    for candidate in candidates:
        candidate_key = candidate.document_number_key
        normalized_name = candidate.normalized_file_name
        if book_key in candidate_key and page_key in candidate_key:
            return candidate
        if book_key in normalized_name and page_key in normalized_name:
            return candidate
    return None


def _match_by_fuzzy_name(
    record: SourceDocument,
    candidates: list[SourceFileCandidate],
) -> tuple[SourceFileCandidate | None, str | None, float | None] | None:
    query_parts = [
        record.document_title,
        record.document_type,
        record.instrument_number,
        record.grantor,
        record.grantee,
    ]
    query = normalize_text(" ".join(str(part) for part in query_parts if part))
    if len(query) < 6:
        return None
    choices = {candidate.normalized_file_name: candidate for candidate in candidates}
    match = process.extractOne(query, choices.keys(), scorer=fuzz.token_set_ratio)
    if not match:
        return None
    matched_name, score, _ = match
    if score < 82:
        return None
    return choices[matched_name], "fuzzy_filename", round(score / 100, 3)


def _apply_source_match(
    record: SourceDocument,
    candidate: SourceFileCandidate,
    method: str | None,
    confidence: float | None,
) -> None:
    record.matched_source_file = candidate.display_name
    record.source_match_method = method
    record.source_match_confidence = confidence
    record.source_trace["matched_source_file"] = candidate.display_name
    record.source_trace["source_match_method"] = method
    record.source_trace["source_match_confidence"] = confidence
    if candidate.archive_path and candidate.member_name:
        record.source_trace["source_package_path"] = str(candidate.archive_path)
        record.source_trace["matched_source_member"] = candidate.member_name
        record.source_trace.pop("matched_source_path", None)
    if candidate.path:
        record.source_trace["matched_source_path"] = str(candidate.path)
        record.source_trace.pop("source_package_path", None)
        record.source_trace.pop("matched_source_member", None)


def _clear_source_match(record: SourceDocument) -> None:
    record.matched_source_file = None
    record.source_match_method = None
    record.source_match_confidence = None
    for key in (
        "matched_source_file",
        "source_match_method",
        "source_match_confidence",
        "source_package_path",
        "matched_source_member",
        "matched_source_path",
    ):
        record.source_trace.pop(key, None)


def _normalize_filename(value: str) -> str:
    return normalize_text(Path(value).as_posix())


def _materialized_file_name(record: SourceDocument, member_name: str) -> str:
    member_path = Path(member_name)
    stem = safe_filename(f"{record.source_document_id}_{member_path.stem}")
    suffix = member_path.suffix.lower() or ".pdf"
    return f"{stem}{suffix}"
