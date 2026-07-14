from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from src.schemas import ProjectMetadata, SourceDocument
from src.utils import clean_cell, enum_value, model_to_dict, normalize_text, parse_date


DEFAULT_COLUMN_ALIASES: dict[str, list[str]] = {
    "document_type": [
        "document type",
        "doc type",
        "doctype",
        "instrument type",
        "type",
    ],
    "document_title": [
        "document title",
        "title",
        "instrument",
        "document name",
        "description",
    ],
    "instrument_number": [
        "instrument number",
        "reception number",
        "recording number",
        "document number",
        "inst no",
        "reception no",
    ],
    "book": ["book", "book no", "bk"],
    "page": ["page", "page no", "pg"],
    "instrument_date": ["instrument date", "document date", "date"],
    "effective_date": ["effective date"],
    "recording_date": ["recording date", "recorded date", "record date"],
    "grantor": ["grantor", "from", "party from"],
    "grantee": ["grantee", "to", "party to"],
    "acreage": ["acreage", "acres"],
    "conveyance": ["conveyance"],
    "legal_description": ["legal description", "legal", "tract", "lands"],
    "comments": ["comments", "comment", "notes", "remarks"],
    "original_file_name": ["file", "filename", "file name", "pdf", "image"],
}


def detect_column_mapping(
    dataframe: pd.DataFrame,
    aliases: dict[str, list[str]] | None = None,
) -> tuple[dict[str, str], dict[str, float]]:
    aliases = aliases or DEFAULT_COLUMN_ALIASES
    normalized_columns = {normalize_text(column): column for column in dataframe.columns}
    mapping: dict[str, str] = {}
    confidence: dict[str, float] = {}

    for field_name, candidates in aliases.items():
        best_column: str | None = None
        best_score = 0.0
        normalized_candidates = [normalize_text(candidate) for candidate in candidates]
        for candidate in normalized_candidates:
            if candidate in normalized_columns:
                best_column = normalized_columns[candidate]
                best_score = 1.0
                break
        if not best_column:
            for candidate in normalized_candidates:
                for normalized_column, original_column in normalized_columns.items():
                    if candidate in normalized_column:
                        best_column = original_column
                        best_score = 0.8
                        break
                if best_column:
                    break
        if best_column:
            mapping[field_name] = best_column
            confidence[field_name] = best_score
        else:
            confidence[field_name] = 0.0

    return mapping, confidence


def _get_row_value(row: pd.Series, mapping: dict[str, str], field_name: str) -> Any:
    column = mapping.get(field_name)
    if not column or column not in row:
        return None
    return row[column]


def create_document_register(
    dataframe: pd.DataFrame,
    column_mapping: dict[str, str] | None = None,
    metadata: ProjectMetadata | None = None,
    source_file_name: str | None = None,
) -> list[SourceDocument]:
    mapping = column_mapping or detect_column_mapping(dataframe)[0]
    records: list[SourceDocument] = []

    for index, row in dataframe.iterrows():
        source_id = f"DOC-{index + 1:06d}"
        raw = {str(column): clean_cell(row[column]) for column in dataframe.columns}
        trace = {
            "document_list_row": int(index) + 2,
            "source_file_name": source_file_name,
            "column_mapping": mapping,
        }
        if metadata:
            trace["project"] = metadata.project_name
            trace["county"] = metadata.county
            trace["state"] = metadata.state

        record = SourceDocument(
            source_document_id=source_id,
            source_row_number=int(index) + 2,
            source_file_name=source_file_name,
            original_file_name=clean_cell(
                _get_row_value(row, mapping, "original_file_name")
            ),
            document_type=clean_cell(_get_row_value(row, mapping, "document_type")),
            document_title=clean_cell(_get_row_value(row, mapping, "document_title")),
            instrument_number=clean_cell(
                _get_row_value(row, mapping, "instrument_number")
            ),
            book=clean_cell(_get_row_value(row, mapping, "book")),
            page=clean_cell(_get_row_value(row, mapping, "page")),
            effective_date=parse_date(_get_row_value(row, mapping, "effective_date")),
            instrument_date=parse_date(
                _get_row_value(row, mapping, "instrument_date")
            ),
            recording_date=parse_date(_get_row_value(row, mapping, "recording_date")),
            grantor=clean_cell(_get_row_value(row, mapping, "grantor")),
            grantee=clean_cell(_get_row_value(row, mapping, "grantee")),
            acreage=clean_cell(_get_row_value(row, mapping, "acreage")),
            conveyance=clean_cell(_get_row_value(row, mapping, "conveyance")),
            legal_description=clean_cell(
                _get_row_value(row, mapping, "legal_description")
            ),
            comments=clean_cell(_get_row_value(row, mapping, "comments")),
            source_trace=trace,
            raw=raw,
        )
        records.append(record)

    return records


EXPORT_COLUMNS = [
    "source_document_id",
    "source_row_number",
    "document_type",
    "document_title",
    "instrument_number",
    "book",
    "page",
    "effective_date",
    "instrument_date",
    "recording_date",
    "grantor",
    "grantee",
    "acreage",
    "conveyance",
    "legal_description",
    "comments",
    "duplicate_of",
    "dedupe_confidence",
    "status",
    "classification_confidence",
    "classification_reason",
    "redline_reason",
    "review_question",
    "lease_status",
    "matched_source_file",
    "source_match_confidence",
    "source_match_method",
    "extracted_text_path",
    "pdf_extraction_status",
    "pdf_extraction_confidence",
    "pdf_page_count",
    "pdf_text_preview",
    "possible_document_type_keywords",
    "possible_legal_description_snippets",
    "possible_lease_primary_term_snippets",
    "source_file_name",
    "original_file_name",
]


def records_to_dataframe(
    records: list[SourceDocument],
    include_raw: bool = False,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for record in records:
        payload = model_to_dict(record)
        row = {
            column: _export_value(enum_value(payload.get(column)))
            for column in EXPORT_COLUMNS
        }
        if include_raw:
            row["raw"] = payload.get("raw", {})
            row["source_trace"] = payload.get("source_trace", {})
        rows.append(row)
    return pd.DataFrame(rows, columns=EXPORT_COLUMNS + (["raw", "source_trace"] if include_raw else []))


def export_document_register(
    records: list[SourceDocument],
    output_path: str | Path,
    include_raw: bool = False,
) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    records_to_dataframe(records, include_raw=include_raw).to_excel(
        output_path, index=False
    )
    return output_path


def _export_value(value: Any) -> Any:
    if isinstance(value, list):
        return " | ".join(str(item) for item in value if item not in (None, ""))
    return value
