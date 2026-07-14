"""LLM-powered structured field extraction via Anthropic Claude API.

Produces CONVEYANCE and COMMENTS in the exact PLM MOR template format.
API key is read from ANTHROPIC_API_KEY env variable — never embedded in code.
Model is read from PLM_LLM_MODEL env variable (default: claude-haiku-4-5-20251001).
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from src.schemas import SourceDocument
from src.utils import get_logger


logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_MODEL = "claude-haiku-4-5-20251001"
LLM_MODEL_ENV = "PLM_LLM_MODEL"

MAX_OCR_CHARS = 4000
MAX_RETRIES = 3
RETRY_BASE_DELAY = 2.0

HIGH_CONFIDENCE = 0.85
LOW_CONFIDENCE_THRESHOLD = 0.60
CACHE_SCHEMA_VERSION = "v3"


# ---------------------------------------------------------------------------
# Pydantic output models
# ---------------------------------------------------------------------------

class LLMFieldResult(BaseModel):
    value: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    provenance: str | None = None


class LLMExtractionResult(BaseModel):
    source_document_id: str
    conveyance: LLMFieldResult = Field(default_factory=LLMFieldResult)
    comments: LLMFieldResult = Field(default_factory=LLMFieldResult)
    grantor_exact: LLMFieldResult = Field(default_factory=LLMFieldResult)
    grantee_exact: LLMFieldResult = Field(default_factory=LLMFieldResult)
    instrument_effect: LLMFieldResult = Field(default_factory=LLMFieldResult)
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    error: str | None = None


# ---------------------------------------------------------------------------
# Custom error
# ---------------------------------------------------------------------------

class LLMConfigError(RuntimeError):
    """Raised when ANTHROPIC_API_KEY is absent or the anthropic package is missing."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_fields_for_record(
    record: SourceDocument,
    ocr_text: str,
    cache_dir: str | Path | None = None,
) -> LLMExtractionResult:
    """Call Claude to extract conveyance and comments in PLM format.

    Returns a result with `error` set on failure — never raises (except LLMConfigError).
    """
    model = os.environ.get(LLM_MODEL_ENV, DEFAULT_MODEL)

    if cache_dir:
        cached = _load_cache(record.source_document_id, model, cache_dir)
        if cached is not None:
            logger.debug("LLM cache hit: %s", record.source_document_id)
            return cached

    try:
        result = _call_claude(record, ocr_text, model)
    except LLMConfigError:
        raise
    except Exception as exc:
        logger.warning("LLM extraction failed for %s: %s", record.source_document_id, exc)
        result = LLMExtractionResult(
            source_document_id=record.source_document_id,
            model=model,
            error=str(exc),
        )

    if cache_dir and not result.error:
        _save_cache(record.source_document_id, model, result, cache_dir)

    return result


def apply_llm_extraction_to_record(
    record: SourceDocument,
    result: LLMExtractionResult,
) -> list[str]:
    """Write LLM fields to record. Returns list of QA warning codes to emit."""
    qa_codes: list[str] = []
    record.source_trace["llm_extraction"] = result.model_dump()
    record.llm_extraction_model = result.model

    if result.error:
        record.source_trace["llm_extraction_error"] = result.error
        qa_codes.append("LLM_EXTRACTION_FAILED")
        return qa_codes

    qa_codes.extend(_apply_field(record, "conveyance", result.conveyance))
    qa_codes.extend(_apply_field(record, "comments", result.comments))
    _apply_party_field(record, "grantor", result.grantor_exact)
    _apply_party_field(record, "grantee", result.grantee_exact)
    return list(dict.fromkeys(qa_codes))


# ---------------------------------------------------------------------------
# System prompt + tool definition
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a professional oil and gas title analyst formatting data for a Mineral
Ownership Report (MOR) runsheet. Extract exactly two fields from the OCR text.
Return ONLY the result of calling the `extract_title_fields` tool — no prose.

=== CONVEYANCE FORMAT ===
Canonical prefix (based on instrument type), then TWO blank lines, then the legal
description in this format:
  {land portion},
  Township {N}S, Range {N}W,
  {Principal Meridian}, {County} County, {State}
  Containing approximately {N} acres  ← include only if explicitly stated

Canonical prefixes:
  Patent                       → Grant of:
  Deed — full interest         → ARTI to:
  Deed — fractional interest   → an undivided X/Y interest to:
  Mineral Deed — full          → ARTI to:
  Mineral Deed — fractional    → an undivided X/Y interest to:
  Quit Claim Deed — full       → ARTI to:
  Quit Claim Deed — fractional → an undivided X/Y interest to:
  Warranty Deed — full         → ARTI to:
  Warranty Deed — fractional   → an undivided X/Y interest to:
  Oil and Gas Lease            → Lease covering:
  Assignment of OGL            → Assignment of Lease covering:
  Release of OGL               → Release of Lease covering:
  Correction Deed              → Correction of:
  Distribution Deed            → ARTI to:
  Decree / Probate             → operative language, e.g. "The Court orders:"
  Affidavit of Heirship        → ARTI to:  (or fractional if stated)

=== COMMENTS FORMAT ===
Include ONLY title-relevant information. Omit everything else.
- Mineral/coal reservation → quote the operative clause ≤15 words in quotation marks
- Oil and Gas Lease → "Primary Term: N years" on one line, "Royalty: X/Y" on next,
  then ACTIVE / EXPIRED / RELEASED on a third line (determine from context).
- Decree / Probate → court name and brief disposition.
- Correction Deed → purpose, e.g. "Filed to correct the legal description".
- POA / appurtenances → brief note only if title-relevant.
- If NOTHING relevant → set value to exactly "" (empty string).

NEVER put REVIEW, status messages, or pipeline metadata in comments.
NEVER invent content. If you cannot read a value clearly, set confidence < 0.4.

=== GRANTOR / GRANTEE (EXACT TEXT) ===
Extract the granting and receiving parties EXACTLY as written in the instrument
body — not from the county index (which often uses "SURNAME, FIRSTNAME" order).
Preserve: marital status descriptors ("and wife", "husband and wife"),
capacity ("Trustee", "Personal Representative", "Independent Executor"),
"deceased", party roles ("plaintiff", "defendant"), tenancy qualifiers
("as joint tenants", "as tenants in common").
Do NOT reformat or reorder names. If you cannot read a party name clearly,
set confidence < 0.4 and value to null.

=== INSTRUMENT EFFECT ===
Classify the title effect of this instrument using exactly one of:
  CONVEYS_MINERAL    → conveys mineral fee, royalty, or overriding royalty interest
                       (mineral deed, warranty deed, quit claim deed, affidavit of heirship,
                        probate decree, distribution deed, personal representative deed)
  ASSIGNS_OGL        → assigns or transfers a working interest under an oil and gas lease
                       (assignment of oil and gas lease, bill of sale of leasehold)
  RELEASES_LEASE     → releases or terminates an oil and gas lease (release of OGL,
                       partial release of OGL)
  EASEMENT_ONLY      → only creates or modifies a surface easement, right-of-way,
                       road agreement, or surface use agreement; no mineral title effect
  NO_TITLE_EFFECT    → administrative, informational, or non-title instrument: affidavit
                       of production, pooling order, lis pendens (no conveyance), lien,
                       deed of trust, financing statement, tax certificate
  UNCLEAR            → cannot determine from available text

Set confidence >= 0.85 only when the instrument type AND operative language are both
unambiguous. If only the document type header is visible but not the operative clause,
use 0.70 or lower.

=== CONFIDENCE ===
1.0 → read directly from text, unambiguous
0.7 → inferred from context, likely correct
0.4 → damaged/ambiguous text, uncertain
<0.4 → set value to null
"""


_TOOL_DEFINITION: dict[str, Any] = {
    "name": "extract_title_fields",
    "description": (
        "Extract CONVEYANCE and COMMENTS from a title document for a PLM MOR runsheet."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "conveyance": {
                "type": "object",
                "description": "Conveyance field with canonical prefix + legal description.",
                "properties": {
                    "value": {"type": "string"},
                    "confidence": {"type": "number"},
                    "provenance": {"type": "string"},
                },
                "required": ["value", "confidence"],
            },
            "comments": {
                "type": "object",
                "description": "Title-relevant comments only, or empty string.",
                "properties": {
                    "value": {"type": "string"},
                    "confidence": {"type": "number"},
                    "provenance": {"type": "string"},
                },
                "required": ["value", "confidence"],
            },
        },
        "required": ["conveyance", "comments"],
        "additionalProperties": False,
    },
}


_PARTY_FIELD_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "value": {"type": "string"},
        "confidence": {"type": "number"},
        "provenance": {"type": "string"},
    },
    "required": ["value", "confidence"],
}

# Inject party fields into the tool definition at module load time
_TOOL_DEFINITION["input_schema"]["properties"]["grantor_exact"] = {
    **_PARTY_FIELD_SCHEMA,
    "description": "Granting party exactly as written in the instrument body.",
}
_TOOL_DEFINITION["input_schema"]["properties"]["grantee_exact"] = {
    **_PARTY_FIELD_SCHEMA,
    "description": "Receiving party exactly as written in the instrument body.",
}
_TOOL_DEFINITION["input_schema"]["properties"]["instrument_effect"] = {
    "type": "object",
    "description": "Title effect classification of this instrument.",
    "properties": {
        "value": {
            "type": "string",
            "enum": [
                "CONVEYS_MINERAL", "ASSIGNS_OGL", "RELEASES_LEASE",
                "EASEMENT_ONLY", "NO_TITLE_EFFECT", "UNCLEAR",
            ],
        },
        "confidence": {"type": "number"},
        "provenance": {"type": "string"},
    },
    "required": ["value", "confidence"],
}


def _build_user_prompt(record: SourceDocument, ocr_text: str) -> str:
    lines = [
        f"INSTRUMENT TYPE: {record.document_type or 'Unknown'}",
        f"RECEPTION / INSTRUMENT NUMBER: {record.instrument_number or 'N/A'}",
        f"BOOK: {record.book or 'N/A'}   PAGE: {record.page or 'N/A'}",
        f"INDEX GRANTOR: {record.grantor or 'N/A'}",
        f"INDEX GRANTEE: {record.grantee or 'N/A'}",
        f"RECORDING DATE: {record.recording_date or 'N/A'}",
    ]
    meta = record.source_trace.get("project_metadata") or {}
    sec = meta.get("section") or ""
    twp = meta.get("township") or ""
    rng = meta.get("range") or ""
    if sec or twp or rng:
        lines.append(f"PROJECT SECTION / TOWNSHIP / RANGE: {sec} / {twp} / {rng}")

    lines += [
        "",
        "=== OCR TEXT (first 4 000 chars) ===",
        ocr_text[:MAX_OCR_CHARS],
        "=== END OCR TEXT ===",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# API call with retry
# ---------------------------------------------------------------------------

def _call_claude(
    record: SourceDocument,
    ocr_text: str,
    model: str,
) -> LLMExtractionResult:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise LLMConfigError(
            "ANTHROPIC_API_KEY is not set. "
            "Export the variable before running LLM extraction."
        )

    import anthropic  # noqa: PLC0415 — lazy import; anthropic is optional

    client = anthropic.Anthropic(api_key=api_key)
    user_prompt = _build_user_prompt(record, ocr_text)
    last_exc: Exception | None = None

    for attempt in range(MAX_RETRIES):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=1024,
                system=_SYSTEM_PROMPT,
                tools=[_TOOL_DEFINITION],
                tool_choice={"type": "tool", "name": "extract_title_fields"},
                messages=[{"role": "user", "content": user_prompt}],
            )
            return _parse_response(record.source_document_id, response, model)
        except anthropic.RateLimitError as exc:
            last_exc = exc
            delay = RETRY_BASE_DELAY * (2 ** attempt)
            logger.warning(
                "Rate limit (attempt %d/%d) for %s — sleeping %.1fs",
                attempt + 1, MAX_RETRIES, record.source_document_id, delay,
            )
            time.sleep(delay)
        except anthropic.APITimeoutError as exc:
            last_exc = exc
            logger.warning(
                "Timeout (attempt %d/%d) for %s",
                attempt + 1, MAX_RETRIES, record.source_document_id,
            )
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_BASE_DELAY)

    raise last_exc or RuntimeError("LLM call failed after all retries")


def _parse_response(
    source_document_id: str,
    response: Any,
    model: str,
) -> LLMExtractionResult:
    usage = response.usage
    prompt_tokens = getattr(usage, "input_tokens", 0)
    completion_tokens = getattr(usage, "output_tokens", 0)

    tool_block = next(
        (b for b in response.content if getattr(b, "type", None) == "tool_use"),
        None,
    )
    if not tool_block:
        return LLMExtractionResult(
            source_document_id=source_document_id,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            error="No tool_use block in API response.",
        )

    data = tool_block.input or {}
    try:
        conv = data.get("conveyance") or {}
        comm = data.get("comments") or {}
        gran = data.get("grantor_exact") or {}
        gran_ee = data.get("grantee_exact") or {}
        ie = data.get("instrument_effect") or {}
        return LLMExtractionResult(
            source_document_id=source_document_id,
            conveyance=LLMFieldResult(
                value=conv.get("value") or None,
                confidence=float(conv.get("confidence", 0.0)),
                provenance=conv.get("provenance"),
            ),
            comments=LLMFieldResult(
                value=comm.get("value") or None,
                confidence=float(comm.get("confidence", 0.0)),
                provenance=comm.get("provenance"),
            ),
            grantor_exact=LLMFieldResult(
                value=gran.get("value") or None,
                confidence=float(gran.get("confidence", 0.0)),
                provenance=gran.get("provenance"),
            ),
            grantee_exact=LLMFieldResult(
                value=gran_ee.get("value") or None,
                confidence=float(gran_ee.get("confidence", 0.0)),
                provenance=gran_ee.get("provenance"),
            ),
            instrument_effect=LLMFieldResult(
                value=ie.get("value") or None,
                confidence=float(ie.get("confidence", 0.0)),
                provenance=ie.get("provenance"),
            ),
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
    except Exception as exc:
        return LLMExtractionResult(
            source_document_id=source_document_id,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            error=f"Response parse error: {exc}",
        )


# ---------------------------------------------------------------------------
# Field application helpers
# ---------------------------------------------------------------------------

_INSTRUMENT_EFFECT_REVIEW_MARKERS = frozenset({
    "unclear_assignment", "possible_title_effect", "No deterministic rule matched",
})

_PROMOTE_EFFECTS = frozenset({"CONVEYS_MINERAL", "ASSIGNS_OGL"})
_REDLINE_EFFECTS = frozenset({"EASEMENT_ONLY", "NO_TITLE_EFFECT"})


def apply_instrument_effect_reclassification(
    record: "SourceDocument",
    result: LLMExtractionResult,
) -> str | None:
    """Reclassify an uncertain REVIEW record based on instrument_effect.

    Only acts on records sent to REVIEW by assignment/bill-of-sale uncertainty
    or a no-rule-matched fallback.  Returns 'include', 'redline', or None.
    """
    from src.schemas import ClassificationStatus  # lazy to avoid circular at module level

    if record.status != ClassificationStatus.REVIEW:
        return None

    reason = record.classification_reason or ""
    if not any(marker in reason for marker in _INSTRUMENT_EFFECT_REVIEW_MARKERS):
        return None

    ie = result.instrument_effect
    if not ie.value or ie.confidence < HIGH_CONFIDENCE:
        return None

    effect = ie.value
    if effect in _PROMOTE_EFFECTS:
        record.status = ClassificationStatus.INCLUDE_FULL
        record.classification_confidence = ie.confidence
        record.review_question = None
        record.source_trace["reclassified_by"] = "llm_instrument_effect"
        record.source_trace["instrument_effect"] = effect
        record.source_trace["instrument_effect_provenance"] = ie.provenance
        logger.info(
            "instrument_effect: %s -> INCLUDE_FULL (effect=%s conf=%.2f)",
            record.source_document_id, effect, ie.confidence,
        )
        return "include"

    if effect in _REDLINE_EFFECTS:
        record.status = ClassificationStatus.REDLINE
        record.redline_reason = (
            f"LLM instrument_effect={effect}. "
            f"Provenance: {ie.provenance or 'N/A'}"
        )
        record.review_question = None
        record.source_trace["reclassified_by"] = "llm_instrument_effect"
        record.source_trace["instrument_effect"] = effect
        record.source_trace["instrument_effect_provenance"] = ie.provenance
        logger.info(
            "instrument_effect: %s -> REDLINE (effect=%s conf=%.2f)",
            record.source_document_id, effect, ie.confidence,
        )
        return "redline"

    return None


def _apply_party_field(
    record: SourceDocument,
    field_name: str,
    field_result: LLMFieldResult,
) -> None:
    """Overwrite grantor/grantee with exact instrument text if confidence >= HIGH.

    Saves the original index value in source_trace so it is never lost.
    If confidence < HIGH_CONFIDENCE, keeps the index value silently.
    """
    if not field_result.value:
        return
    if field_result.confidence < HIGH_CONFIDENCE:
        return
    original = getattr(record, field_name)
    record.source_trace[f"{field_name}_index"] = original
    setattr(record, field_name, field_result.value)


def _apply_field(
    record: SourceDocument,
    field_name: str,
    field_result: LLMFieldResult,
) -> list[str]:
    """Write one field to the record according to confidence thresholds."""
    if not field_result.value:
        return []

    conf = field_result.confidence
    if conf < LOW_CONFIDENCE_THRESHOLD:
        record.source_trace.setdefault("llm_low_confidence_fields", []).append(field_name)
        return ["LLM_EXTRACTION_LOW_CONFIDENCE"]

    setattr(record, field_name, field_result.value)
    if field_name == "conveyance":
        record.llm_conveyance_confidence = conf
    elif field_name == "comments":
        record.llm_comments_confidence = conf

    if conf < HIGH_CONFIDENCE:
        return ["LLM_EXTRACTION_LOW_CONFIDENCE"]
    return []


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _cache_filename(source_document_id: str, model: str) -> str:
    safe_id = source_document_id.replace("/", "_").replace(":", "_").replace(" ", "_")
    model_tag = model[:20].replace("/", "_")
    return f"{safe_id}_{model_tag}_{CACHE_SCHEMA_VERSION}_llm.json"


def _load_cache(
    source_document_id: str,
    model: str,
    cache_dir: str | Path,
) -> LLMExtractionResult | None:
    path = Path(cache_dir) / _cache_filename(source_document_id, model)
    if not path.exists():
        return None
    try:
        return LLMExtractionResult.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_cache(
    source_document_id: str,
    model: str,
    result: LLMExtractionResult,
    cache_dir: str | Path,
) -> None:
    try:
        cache_path = Path(cache_dir)
        cache_path.mkdir(parents=True, exist_ok=True)
        (cache_path / _cache_filename(source_document_id, model)).write_text(
            result.model_dump_json(indent=2), encoding="utf-8"
        )
    except Exception as exc:
        logger.warning("Could not write LLM cache for %s: %s", source_document_id, exc)
