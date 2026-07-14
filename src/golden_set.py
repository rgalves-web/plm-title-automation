from __future__ import annotations

from datetime import date, datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

import pandas as pd

from src.classifier import classify_document
from src.schemas import SourceDocument
from src.utils import clean_cell, enum_value, normalize_text, parse_date


DEFAULT_GOLDEN_DIR = Path("data/golden_set")
GOLDEN_CLASSIFICATIONS_FILE = "golden_classifications.csv"
GOLDEN_RUNSHEET_ROWS_FILE = "golden_runsheet_rows.csv"

CLASSIFICATION_SOURCE_FIELDS = [
    "source_document_id",
    "source_file_name",
    "source_row_number",
    "document_type",
    "document_title",
    "instrument_number",
    "book",
    "page",
    "instrument_date",
    "recording_date",
    "grantor",
    "grantee",
    "legal_description",
    "comments",
    "duplicate_of",
]
CLASSIFICATION_EXPECTED_FIELDS = [
    "expected_status",
    "expected_redline_reason",
    "expected_review_question",
    "expected_lease_status",
]
CLASSIFICATION_COLUMNS = [
    "golden_id",
    "approved_at",
    "approved_by",
    "project_name",
    *CLASSIFICATION_SOURCE_FIELDS,
    *CLASSIFICATION_EXPECTED_FIELDS,
    "approval_note",
]

RUNSHEET_ROW_FIELDS = [
    "source_document_id",
    "status",
    "instrument_date",
    "recording_date",
    "document_type",
    "grantor",
    "grantee",
    "book",
    "page",
    "instrument_number",
    "comments",
    "redline_reason",
    "lease_status",
    "review_question",
    "duplicate_of",
]
RUNSHEET_COLUMNS = [
    "golden_id",
    "approved_at",
    "approved_by",
    "project_name",
    *RUNSHEET_ROW_FIELDS,
    "approval_note",
]


def golden_classifications_path(golden_dir: str | Path = DEFAULT_GOLDEN_DIR) -> Path:
    return Path(golden_dir) / GOLDEN_CLASSIFICATIONS_FILE


def golden_runsheet_rows_path(golden_dir: str | Path = DEFAULT_GOLDEN_DIR) -> Path:
    return Path(golden_dir) / GOLDEN_RUNSHEET_ROWS_FILE


def load_golden_classifications(
    golden_dir: str | Path = DEFAULT_GOLDEN_DIR,
) -> pd.DataFrame:
    return _read_csv_or_empty(golden_classifications_path(golden_dir), CLASSIFICATION_COLUMNS)


def load_golden_runsheet_rows(
    golden_dir: str | Path = DEFAULT_GOLDEN_DIR,
) -> pd.DataFrame:
    return _read_csv_or_empty(golden_runsheet_rows_path(golden_dir), RUNSHEET_COLUMNS)


def prepare_classification_approval_table(register_df: pd.DataFrame) -> pd.DataFrame:
    table = _copy_columns(register_df, CLASSIFICATION_SOURCE_FIELDS)
    table["status"] = _column_or_blank(register_df, "status")
    table["redline_reason"] = _column_or_blank(register_df, "redline_reason")
    table["review_question"] = _column_or_blank(register_df, "review_question")
    table["lease_status"] = _column_or_blank(register_df, "lease_status")
    table.insert(0, "approved", False)
    table["approval_note"] = ""
    return table


def prepare_runsheet_approval_table(register_df: pd.DataFrame) -> pd.DataFrame:
    table = _copy_columns(register_df, RUNSHEET_ROW_FIELDS)
    table.insert(0, "approved", False)
    table["approval_note"] = ""
    return table


def append_golden_classifications(
    approval_df: pd.DataFrame,
    golden_dir: str | Path = DEFAULT_GOLDEN_DIR,
    project_name: str = "",
    approved_by: str = "",
) -> int:
    selected = _approved_rows(approval_df)
    rows = [
        _classification_row_from_approval(row, project_name, approved_by)
        for _, row in selected.iterrows()
    ]
    return _upsert_rows(
        golden_classifications_path(golden_dir),
        CLASSIFICATION_COLUMNS,
        rows,
    )


def append_golden_runsheet_rows(
    approval_df: pd.DataFrame,
    golden_dir: str | Path = DEFAULT_GOLDEN_DIR,
    project_name: str = "",
    approved_by: str = "",
) -> int:
    selected = _approved_rows(approval_df)
    rows = [
        _runsheet_row_from_approval(row, project_name, approved_by)
        for _, row in selected.iterrows()
    ]
    return _upsert_rows(
        golden_runsheet_rows_path(golden_dir),
        RUNSHEET_COLUMNS,
        rows,
    )


def compare_classifier_to_golden(
    golden_dir: str | Path = DEFAULT_GOLDEN_DIR,
    rules: dict[str, Any] | None = None,
) -> dict[str, Any]:
    golden_df = load_golden_classifications(golden_dir)
    drifts: list[dict[str, Any]] = []

    for _, row in golden_df.iterrows():
        record = _source_document_from_golden(row)
        classify_document(record, rules=rules)
        actuals = {
            "expected_status": enum_value(record.status),
            "expected_redline_reason": record.redline_reason,
            "expected_review_question": record.review_question,
            "expected_lease_status": enum_value(record.lease_status),
        }
        for expected_field, actual_value in actuals.items():
            expected_value = _cell(row, expected_field)
            if expected_field == "expected_status" or expected_value:
                if _string(actual_value) != _string(expected_value):
                    drifts.append(
                        _drift_row(
                            row,
                            expected_field.replace("expected_", ""),
                            expected_value,
                            actual_value,
                        )
                    )

    return {
        "passed": not drifts,
        "total_examples": int(len(golden_df)),
        "drift_count": int(len(drifts)),
        "drifts": drifts,
    }


def drift_report_to_dataframe(report: dict[str, Any]) -> pd.DataFrame:
    return pd.DataFrame(
        report.get("drifts", []),
        columns=[
            "golden_id",
            "source_document_id",
            "field",
            "expected",
            "actual",
            "document_type",
            "document_title",
            "instrument_number",
        ],
    )


def _classification_row_from_approval(
    row: pd.Series,
    project_name: str,
    approved_by: str,
) -> dict[str, Any]:
    payload = {
        "approved_at": _approved_at(),
        "approved_by": approved_by,
        "project_name": project_name,
    }
    for field in CLASSIFICATION_SOURCE_FIELDS:
        payload[field] = _string(_cell(row, field))
    payload["instrument_date"] = _date_string(_cell(row, "instrument_date"))
    payload["recording_date"] = _date_string(_cell(row, "recording_date"))
    payload["expected_status"] = _string(_cell(row, "expected_status") or _cell(row, "status"))
    payload["expected_redline_reason"] = _string(
        _cell(row, "expected_redline_reason") or _cell(row, "redline_reason")
    )
    payload["expected_review_question"] = _string(
        _cell(row, "expected_review_question") or _cell(row, "review_question")
    )
    payload["expected_lease_status"] = _string(
        _cell(row, "expected_lease_status") or _cell(row, "lease_status")
    )
    payload["approval_note"] = _string(_cell(row, "approval_note"))
    payload["golden_id"] = _golden_id(payload, CLASSIFICATION_SOURCE_FIELDS)
    return _ordered_row(payload, CLASSIFICATION_COLUMNS)


def _runsheet_row_from_approval(
    row: pd.Series,
    project_name: str,
    approved_by: str,
) -> dict[str, Any]:
    payload = {
        "approved_at": _approved_at(),
        "approved_by": approved_by,
        "project_name": project_name,
    }
    for field in RUNSHEET_ROW_FIELDS:
        payload[field] = _string(_cell(row, field))
    payload["instrument_date"] = _date_string(_cell(row, "instrument_date"))
    payload["recording_date"] = _date_string(_cell(row, "recording_date"))
    payload["approval_note"] = _string(_cell(row, "approval_note"))
    payload["golden_id"] = _golden_id(payload, RUNSHEET_ROW_FIELDS)
    return _ordered_row(payload, RUNSHEET_COLUMNS)


def _source_document_from_golden(row: pd.Series) -> SourceDocument:
    source_row_number = _cell(row, "source_row_number")
    try:
        source_row_number = int(float(source_row_number))
    except (TypeError, ValueError):
        source_row_number = 0

    return SourceDocument(
        source_document_id=_cell(row, "source_document_id") or _cell(row, "golden_id"),
        source_row_number=source_row_number,
        source_file_name=clean_cell(_cell(row, "source_file_name")),
        document_type=clean_cell(_cell(row, "document_type")),
        document_title=clean_cell(_cell(row, "document_title")),
        instrument_number=clean_cell(_cell(row, "instrument_number")),
        book=clean_cell(_cell(row, "book")),
        page=clean_cell(_cell(row, "page")),
        instrument_date=parse_date(_cell(row, "instrument_date")),
        recording_date=parse_date(_cell(row, "recording_date")),
        grantor=clean_cell(_cell(row, "grantor")),
        grantee=clean_cell(_cell(row, "grantee")),
        legal_description=clean_cell(_cell(row, "legal_description")),
        comments=clean_cell(_cell(row, "comments")),
        duplicate_of=clean_cell(_cell(row, "duplicate_of")),
    )


def _drift_row(
    row: pd.Series,
    field: str,
    expected: Any,
    actual: Any,
) -> dict[str, Any]:
    return {
        "golden_id": _cell(row, "golden_id"),
        "source_document_id": _cell(row, "source_document_id"),
        "field": field,
        "expected": _string(expected),
        "actual": _string(actual),
        "document_type": _cell(row, "document_type"),
        "document_title": _cell(row, "document_title"),
        "instrument_number": _cell(row, "instrument_number"),
    }


def _copy_columns(dataframe: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    copied = pd.DataFrame()
    for column in columns:
        copied[column] = _column_or_blank(dataframe, column)
    return copied


def _column_or_blank(dataframe: pd.DataFrame, column: str) -> pd.Series:
    if column in dataframe:
        return dataframe[column]
    return pd.Series([""] * len(dataframe), index=dataframe.index)


def _approved_rows(dataframe: pd.DataFrame) -> pd.DataFrame:
    if "approved" not in dataframe:
        return dataframe.copy()
    mask = dataframe["approved"].apply(_is_truthy)
    return dataframe[mask].copy()


def _upsert_rows(path: Path, columns: list[str], rows: list[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        _read_csv_or_empty(path, columns).to_csv(path, index=False)
        return 0

    existing = _read_csv_or_empty(path, columns)
    incoming = pd.DataFrame(rows, columns=columns)
    if not existing.empty:
        incoming_ids = set(incoming["golden_id"].astype(str))
        existing = existing[~existing["golden_id"].astype(str).isin(incoming_ids)]
    combined = pd.concat([existing, incoming], ignore_index=True)
    combined.to_csv(path, index=False)
    return len(incoming)


def _read_csv_or_empty(path: Path, columns: list[str]) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=columns)
    dataframe = pd.read_csv(path, dtype=str, keep_default_na=False)
    for column in columns:
        if column not in dataframe:
            dataframe[column] = ""
    return dataframe[columns]


def _ordered_row(payload: dict[str, Any], columns: list[str]) -> dict[str, Any]:
    return {column: _string(payload.get(column)) for column in columns}


def _golden_id(payload: dict[str, Any], fields: list[str]) -> str:
    parts = [normalize_text(payload.get(field, "")) for field in fields]
    digest = sha256("|".join(parts).encode("utf-8")).hexdigest()
    return digest[:16]


def _cell(row: pd.Series, field: str) -> Any:
    if field not in row:
        return ""
    value = row[field]
    if pd.isna(value):
        return ""
    return value


def _string(value: Any) -> str:
    value = enum_value(value)
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value).strip()


def _date_string(value: Any) -> str:
    parsed = parse_date(value)
    return parsed.isoformat() if parsed else _string(value)


def _is_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _string(value).lower() in {"1", "true", "yes", "y", "approved", "x"}


def _approved_at() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
