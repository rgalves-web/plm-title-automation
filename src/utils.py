from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml


LOGGER_NAME = "plm_title_automation"


def get_logger(name: str | None = None) -> logging.Logger:
    logger = logging.getLogger(name or LOGGER_NAME)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s")
        )
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


def ensure_dirs(*paths: str | Path) -> None:
    for path in paths:
        Path(path).mkdir(parents=True, exist_ok=True)


def read_yaml(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return data


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    with Path(path).open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, default=str)


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower()
    text = re.sub(r"[_\-/]+", " ", text)
    text = re.sub(r"[^a-z0-9&' ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def clean_cell(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and value != value:
        return None
    text = str(value).strip()
    return text or None


def parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = clean_cell(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("/", "-"))
        return parsed.date()
    except ValueError:
        pass
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%m-%d-%Y", "%m.%d.%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def safe_filename(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug or "untitled"


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def model_to_dict(model: Any) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def enum_value(value: Any) -> Any:
    return getattr(value, "value", value)
