"""LLM-first parser for a RAW oil & gas lease (or its recorded memorandum).

Mirrors title_opinion_parser.py's OCR + Claude tool-use + JSON-cache pattern,
but its schema targets the lease-review fields a landman fills from the lease
instrument itself: royalty, primary term, shut-in royalty, pooling clause,
Pugh clause (surface and depth), depth limitations, continuous development, and
recording information. Every field carries its own confidence and a provenance
source-span quote so nothing is asserted without a citation, and any field not
found in the document stays null (never invented).
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from src.llm_extractor import (
    DEFAULT_MODEL,
    LLM_MODEL_ENV,
    LLMConfigError,
    LLMFieldResult,
    MAX_RETRIES,
    RETRY_BASE_DELAY,
)
from src.utils import get_logger

logger = get_logger(__name__)

DD_LEASE_CACHE_SCHEMA_VERSION = "dd_lease_v1"
MAX_OCR_CHARS = 16000


class LeaseExtraction(BaseModel):
    source_pdf_path: str = ""
    lease_key: str = ""
    lessor: LLMFieldResult = Field(default_factory=LLMFieldResult)
    lessee: LLMFieldResult = Field(default_factory=LLMFieldResult)
    lease_date: LLMFieldResult = Field(default_factory=LLMFieldResult)
    recording_info: LLMFieldResult = Field(default_factory=LLMFieldResult)
    legal_description: LLMFieldResult = Field(default_factory=LLMFieldResult)
    gross_acres: LLMFieldResult = Field(default_factory=LLMFieldResult)
    royalty: LLMFieldResult = Field(default_factory=LLMFieldResult)
    primary_term: LLMFieldResult = Field(default_factory=LLMFieldResult)
    shut_in_royalty: LLMFieldResult = Field(default_factory=LLMFieldResult)
    pooling_clause: LLMFieldResult = Field(default_factory=LLMFieldResult)
    horizontal_pugh: LLMFieldResult = Field(default_factory=LLMFieldResult)
    vertical_pugh: LLMFieldResult = Field(default_factory=LLMFieldResult)
    depth_limitations: LLMFieldResult = Field(default_factory=LLMFieldResult)
    continuous_development: LLMFieldResult = Field(default_factory=LLMFieldResult)
    document_kind: LLMFieldResult = Field(default_factory=LLMFieldResult)
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    error: str | None = None

    def min_confidence(self) -> float:
        vals = [
            f.confidence
            for f in (self.royalty, self.primary_term, self.recording_info)
            if f and f.value
        ]
        return min(vals) if vals else 0.0


_SYSTEM_PROMPT = """\
You are a professional oil and gas landman extracting lease-review data from a
scanned OIL & GAS LEASE or its recorded MEMORANDUM (OCR text — expect
occasional character errors). Return ONLY the result of calling the
`extract_lease` tool.

Extract each field EXACTLY as written in the instrument. For every field also
return `provenance`: a short verbatim quote (the source span) from the OCR text
that supports the value. If a field is NOT stated in this document, leave its
value null and set confidence below 0.4 — never infer, compute, or invent a
value that is not present.

FIELDS:
- royalty: the royalty fraction/percentage and what it covers (e.g. "1/5 (20%)
  on oil, gas and casinghead gas").
- primary_term: the primary term length (e.g. "3 years", "five (5) years").
- shut_in_royalty: shut-in royalty amount/terms if stated.
- pooling_clause: whether pooling is authorized and any acreage/tolerance limits.
- horizontal_pugh: a horizontal (surface-acreage) Pugh clause severing
  non-pooled/non-producing acreage, if present.
- vertical_pugh / depth_limitations: a vertical (depth) Pugh clause or depth
  severance below the deepest producing/permitted depth, if present.
- continuous_development: continuous drilling/development obligation, if present.
- recording_info: the recording reference (e.g. "Volume 402, Page 50, Real
  Records of Montague County, Texas", plus filing date if shown). For a
  MEMORANDUM this is usually stamped on the document.
- lessor, lessee, lease_date, legal_description, gross_acres.
- document_kind: "LEASE" or "MEMORANDUM" — which instrument this OCR is.

CONFIDENCE: 1.0 read directly, unambiguous; 0.7 inferred from context; 0.4
damaged/ambiguous; <0.4 -> value null.
"""

_FIELD_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "value": {"type": "string"},
        "confidence": {"type": "number"},
        "provenance": {"type": "string"},
    },
    "required": ["value", "confidence"],
}

_LEASE_FIELDS = (
    "lessor", "lessee", "lease_date", "recording_info", "legal_description",
    "gross_acres", "royalty", "primary_term", "shut_in_royalty",
    "pooling_clause", "horizontal_pugh", "vertical_pugh", "depth_limitations",
    "continuous_development", "document_kind",
)

_TOOL_DEFINITION: dict[str, Any] = {
    "name": "extract_lease",
    "description": "Extract lease-review fields from an oil & gas lease or its recorded memorandum.",
    "input_schema": {
        "type": "object",
        "properties": {field: _FIELD_SCHEMA for field in _LEASE_FIELDS},
        "required": [],
        "additionalProperties": False,
    },
}


def _cache_path(lease_key: str, model: str, cache_dir: Path) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in lease_key)[:80]
    model_tag = model.replace(".", "").replace("/", "_")[:24]
    return cache_dir / f"{safe}_{model_tag}_{DD_LEASE_CACHE_SCHEMA_VERSION}_lease.json"


def parse_lease(
    pdf_path: str | Path,
    lease_key: str,
    work_dir: str | Path,
    cache_dir: str | Path | None = None,
) -> LeaseExtraction:
    pdf_path = Path(pdf_path)
    model = os.environ.get(LLM_MODEL_ENV, DEFAULT_MODEL)

    if cache_dir:
        cache_dir = Path(cache_dir)
        cached = _cache_path(lease_key, model, cache_dir)
        if cached.exists():
            try:
                return LeaseExtraction(**json.loads(cached.read_text(encoding="utf-8")))
            except Exception:
                pass

    from src.pdf_reader import extract_document
    from src.pipeline import _OCR_CACHE_DIR

    try:
        extraction = extract_document(pdf_path, text_cache_dir=_OCR_CACHE_DIR)
        ocr_text = extraction.full_text or ""
    except Exception as exc:
        return LeaseExtraction(source_pdf_path=str(pdf_path), lease_key=lease_key,
                               model=model, error=f"OCR failed: {exc}")
    if not ocr_text.strip():
        return LeaseExtraction(source_pdf_path=str(pdf_path), lease_key=lease_key,
                               model=model, error="OCR produced no text (image-only, needs manual review).")

    try:
        result = _call_claude(str(pdf_path), lease_key, ocr_text, model)
    except LLMConfigError:
        raise
    except Exception as exc:
        logger.warning("Lease extraction failed for %s: %s", lease_key, exc)
        return LeaseExtraction(source_pdf_path=str(pdf_path), lease_key=lease_key,
                               model=model, error=str(exc))

    if cache_dir and not result.error:
        cache_dir.mkdir(parents=True, exist_ok=True)
        _cache_path(lease_key, model, cache_dir).write_text(
            json.dumps(result.model_dump(mode="json")), encoding="utf-8")
    return result


def _call_claude(pdf_path: str, lease_key: str, ocr_text: str, model: str) -> LeaseExtraction:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise LLMConfigError("ANTHROPIC_API_KEY is not set.")
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    user_prompt = (
        f"LEASE KEY: {lease_key}\n\n=== OCR TEXT ===\n{ocr_text[:MAX_OCR_CHARS]}\n=== END OCR TEXT ==="
    )
    last_exc: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=8000,
                system=_SYSTEM_PROMPT,
                tools=[_TOOL_DEFINITION],
                tool_choice={"type": "tool", "name": "extract_lease"},
                messages=[{"role": "user", "content": user_prompt}],
            )
            return _parse_response(pdf_path, lease_key, response, model)
        except anthropic.RateLimitError as exc:
            last_exc = exc
            time.sleep(RETRY_BASE_DELAY * (2 ** attempt))
        except anthropic.APITimeoutError as exc:
            last_exc = exc
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_BASE_DELAY)
    raise last_exc or RuntimeError("Lease extraction call failed after all retries")


def _field(data: dict[str, Any] | None) -> LLMFieldResult:
    data = data or {}
    return LLMFieldResult(
        value=data.get("value") or None,
        confidence=float(data.get("confidence", 0.0)),
        provenance=data.get("provenance"),
    )


def _parse_response(pdf_path: str, lease_key: str, response: Any, model: str) -> LeaseExtraction:
    usage = response.usage
    tool_input: dict[str, Any] = {}
    for block in response.content:
        if getattr(block, "type", None) == "tool_use" and block.name == "extract_lease":
            tool_input = block.input or {}
            break
    if getattr(response, "stop_reason", None) == "max_tokens" and not tool_input:
        return LeaseExtraction(
            source_pdf_path=pdf_path, lease_key=lease_key, model=model,
            error="LLM response truncated at max_tokens.")
    return LeaseExtraction(
        source_pdf_path=pdf_path,
        lease_key=lease_key,
        model=model,
        prompt_tokens=getattr(usage, "input_tokens", 0),
        completion_tokens=getattr(usage, "output_tokens", 0),
        **{field: _field(tool_input.get(field)) for field in _LEASE_FIELDS},
    )
