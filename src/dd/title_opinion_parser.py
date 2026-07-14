"""LLM-first Title Opinion PDF parser for Due Diligence.

Reuses the src/llm_extractor.py tool-use + retry + JSON-cache pattern, but as
its own module with its own cache namespace (DD_TO_CACHE_SCHEMA_VERSION) since
the extraction shape is unrelated to MOR's conveyance/comments schema. OCR
reuses the shared persistent cache from src/pipeline.py so a TO PDF is never
re-OCR'd across runs.

The LLM transcribes fraction text and party/company names verbatim — it never
computes or sums interests. Which WORKING INTEREST row belongs to the named
Seller is resolved in Python via fuzzy name matching, not by the LLM, so the
Seller-row selection is deterministic and auditable.
"""
from __future__ import annotations

import os
import shutil
import time
import zipfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from rapidfuzz import fuzz

from src.dd.manifest import TitleOpinionRef
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

DD_TO_CACHE_SCHEMA_VERSION = "dd_to_v2"  # v2: full lease-schedule extraction merged in
MAX_OCR_CHARS = 16000
MAX_SCHEDULE_OCR_CHARS = 48000  # the lease schedule can span many pages
SELLER_MATCH_THRESHOLD = 80  # rapidfuzz token_sort_ratio


# ---------------------------------------------------------------------------
# Pydantic result schema
# ---------------------------------------------------------------------------

class TOPartyInterest(BaseModel):
    party: str
    fraction_text: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    provenance: str | None = None


class TOWorkingInterestRow(BaseModel):
    company: str
    operating_interest_text: str
    net_revenue_interest_text: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    provenance: str | None = None


class TOLeaseBlock(BaseModel):
    lease_identifier: LLMFieldResult = Field(default_factory=LLMFieldResult)
    lease_date: LLMFieldResult = Field(default_factory=LLMFieldResult)
    recording_info: LLMFieldResult = Field(default_factory=LLMFieldResult)
    lessor: LLMFieldResult = Field(default_factory=LLMFieldResult)
    lessee: LLMFieldResult = Field(default_factory=LLMFieldResult)
    land_covered: LLMFieldResult = Field(default_factory=LLMFieldResult)
    interest_covered: LLMFieldResult = Field(default_factory=LLMFieldResult)
    primary_term: LLMFieldResult = Field(default_factory=LLMFieldResult)
    royalty: LLMFieldResult = Field(default_factory=LLMFieldResult)
    shut_in_royalty: LLMFieldResult = Field(default_factory=LLMFieldResult)
    pooling: LLMFieldResult = Field(default_factory=LLMFieldResult)
    pugh_clause: LLMFieldResult = Field(default_factory=LLMFieldResult)
    continuous_development: LLMFieldResult = Field(default_factory=LLMFieldResult)
    depth_limitations: LLMFieldResult = Field(default_factory=LLMFieldResult)


class TOTract(BaseModel):
    tract_legal_description: LLMFieldResult = Field(default_factory=LLMFieldResult)
    tract_gross_acres: LLMFieldResult = Field(default_factory=LLMFieldResult)
    certification_date: LLMFieldResult = Field(default_factory=LLMFieldResult)
    letter_date: LLMFieldResult = Field(default_factory=LLMFieldResult)
    surface_owners: list[TOPartyInterest] = Field(default_factory=list)
    mineral_owners: list[TOPartyInterest] = Field(default_factory=list)
    royalty_owners: list[TOPartyInterest] = Field(default_factory=list)
    overriding_royalty_owners: list[TOPartyInterest] = Field(default_factory=list)
    working_interest_table: list[TOWorkingInterestRow] = Field(default_factory=list)
    seller_working_interest: TOWorkingInterestRow | None = None
    leases: list[TOLeaseBlock] = Field(default_factory=list)
    requirements: list[LLMFieldResult] = Field(default_factory=list)
    comments: list[LLMFieldResult] = Field(default_factory=list)
    predicted_unit_coverage: LLMFieldResult = Field(default_factory=LLMFieldResult)


class TitleOpinionExtraction(BaseModel):
    file_number: str
    source_pdf_path: str = ""
    pdf_available: bool = True
    tracts: list[TOTract] = Field(default_factory=list)
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    error: str | None = None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_title_opinion(
    to_ref: TitleOpinionRef,
    target_unit_name: str,
    seller_name: str | None,
    work_dir: str | Path,
    cache_dir: str | Path | None = None,
) -> TitleOpinionExtraction:
    """Parse one Title Opinion PDF. Never calls OCR/LLM when no PDF is available."""
    if not to_ref.pdf_available or not to_ref.pdf_path:
        return TitleOpinionExtraction(
            file_number=to_ref.file_number,
            pdf_available=False,
            error="No PDF available for this title opinion file number.",
        )

    model = os.environ.get(LLM_MODEL_ENV, DEFAULT_MODEL)

    if cache_dir:
        cached = _load_cache(to_ref.file_number, model, cache_dir)
        if cached is not None:
            logger.debug("TO cache hit: %s", to_ref.file_number)
            return cached

    pdf_path = _materialize_to_pdf(to_ref, Path(work_dir))

    from src.pdf_reader import extract_document
    from src.pipeline import _OCR_CACHE_DIR

    extraction = extract_document(pdf_path, text_cache_dir=_OCR_CACHE_DIR)
    ocr_text = extraction.full_text or ""

    try:
        result = _call_claude(
            to_ref.file_number, str(pdf_path), ocr_text, target_unit_name, model
        )
    except LLMConfigError:
        raise
    except Exception as exc:
        logger.warning("TO extraction failed for %s: %s", to_ref.file_number, exc)
        result = TitleOpinionExtraction(
            file_number=to_ref.file_number,
            source_pdf_path=str(pdf_path),
            model=model,
            error=str(exc),
        )

    # Second, bounded pass: extract the FULL lease-analysis schedule so dense
    # opinions (Cox: 20+ leases) are not truncated by the main call. Merge the
    # fuller lease set onto the primary tract.
    if not result.error and result.tracts:
        try:
            schedule = extract_lease_schedule(to_ref.file_number, ocr_text, model)
        except LLMConfigError:
            raise
        except Exception as exc:
            logger.warning("Lease-schedule extraction failed for %s: %s", to_ref.file_number, exc)
            schedule = []
        if len(schedule) > len(result.tracts[0].leases):
            result.tracts[0].leases = schedule

    _resolve_seller_working_interest(result, seller_name)

    if cache_dir and not result.error:
        _save_cache(to_ref.file_number, model, result, cache_dir)

    return result


def extract_lease_schedule(file_number: str, ocr_text: str, model: str) -> list[TOLeaseBlock]:
    """Dedicated LLM call that extracts ONLY the lease-analysis schedule (every
    lease block), so a dense opinion never truncates. Bounded output schema,
    full-document OCR context. Returns [] on any failure — the caller keeps the
    main extraction's leases in that case."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise LLMConfigError("ANTHROPIC_API_KEY is not set.")
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    prompt = (
        f"TITLE OPINION FILE NUMBER: {file_number}\n\n=== OCR TEXT ===\n"
        f"{ocr_text[:MAX_SCHEDULE_OCR_CHARS]}\n=== END OCR TEXT ==="
    )
    last_exc: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=16000,
                system=_LEASE_SCHEDULE_SYSTEM,
                tools=[_LEASE_SCHEDULE_TOOL],
                tool_choice={"type": "tool", "name": "extract_lease_schedule"},
                messages=[{"role": "user", "content": prompt}],
            )
            block = next((b for b in response.content if getattr(b, "type", None) == "tool_use"), None)
            if not block:
                return []
            leases = (block.input or {}).get("leases") or []
            return [TOLeaseBlock(**{k: _field(v) for k, v in lease.items()}) for lease in leases]
        except anthropic.RateLimitError as exc:
            last_exc = exc
            time.sleep(RETRY_BASE_DELAY * (2 ** attempt))
        except anthropic.APITimeoutError as exc:
            last_exc = exc
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_BASE_DELAY)
    if last_exc:
        raise last_exc
    return []


def _resolve_seller_working_interest(
    result: TitleOpinionExtraction, seller_name: str | None
) -> None:
    """Pick the WORKING INTEREST row matching seller_name, by fuzzy name match.

    Deterministic and code-driven on purpose — the LLM only transcribes the
    table, it never decides which row is the Seller's.
    """
    if not seller_name:
        return
    for tract in result.tracts:
        if not tract.working_interest_table:
            continue
        best_row = None
        best_score = 0.0
        for row in tract.working_interest_table:
            score = fuzz.token_sort_ratio(row.company.upper(), seller_name.upper())
            if score > best_score:
                best_score = score
                best_row = row
        if best_row is not None and best_score >= SELLER_MATCH_THRESHOLD:
            tract.seller_working_interest = best_row


def _materialize_to_pdf(to_ref: TitleOpinionRef, work_dir: Path) -> Path:
    pdf_path = Path(to_ref.pdf_path)
    if pdf_path.suffix.lower() == ".pdf":
        return pdf_path

    work_dir.mkdir(parents=True, exist_ok=True)
    target = work_dir / f"{to_ref.file_number}.pdf"
    if target.exists():
        return target

    with zipfile.ZipFile(pdf_path) as zf:
        pdf_members = [n for n in zf.namelist() if n.lower().endswith(".pdf")]
        if not pdf_members:
            raise FileNotFoundError(f"No PDF member found in {pdf_path}")
        with zf.open(pdf_members[0]) as src, target.open("wb") as dst:
            shutil.copyfileobj(src, dst)
    return target


# ---------------------------------------------------------------------------
# System prompt + tool definition
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a professional oil and gas title analyst extracting structured data
from a scanned Title Opinion letter (OCR text — expect occasional character
errors). Return ONLY the result of calling the `extract_title_opinion` tool.

A title opinion usually certifies ONE tract; rarely it covers more than one
legal description — produce one entry in `tracts` per certified tract.

=== TRACT GROSS ACRES ===
`tract_gross_acres` is the tract's total gross surface acreage as a bare
number (e.g. "119.2"), taken from the legal description (e.g. "119.2 acres,
more or less, out of the Samuel Cable Survey"). Transcribe only the number —
no "acres" suffix, no commas. If the tract states multiple acreages, use the
overall tract total. Leave null with confidence < 0.4 if no acreage is stated.

=== CERTIFICATION DATE vs LETTER DATE ===
The letter has TWO distinct dates that are easy to confuse:
  - `letter_date`: the date at the top of the letter (often the latest date,
    near the addressee block).
  - `certification_date`: the date in the opinion's own certification
    language, typically phrased "...we are of the opinion that as of
    [DATE], the Land was owned:" or "...as of [DATE], title to the Land was
    vested in...". This is the date supplemental title research starts FROM
    and is NOT the same as `letter_date`. If you cannot find this exact
    certification phrase, set confidence below 0.4 and leave the value null —
    do NOT substitute the letter date.

=== OWNERSHIP BLOCKS ===
Transcribe each named party and their fraction EXACTLY as printed in the
SURFACE / MINERALS / ROYALTY / OVERRIDING ROYALTY sections. fraction_text is
the literal text (e.g. "1/2", "1/2 x 1/8", "0.0625000") — never compute,
simplify, or sum it.

=== WORKING INTEREST TABLE ===
Transcribe each company row's WORKING (operating) interest and NET REVENUE
interest exactly as printed. Do not compute a total row yourself even if one
is printed — only transcribe per-company rows.

CRITICAL COLUMN MAPPING: these tables usually print, per company, an NRI
CALCULATION FORMULA followed by TWO decimal columns — first the WORKING
INTEREST, then the NET REVENUE INTEREST. Example row as OCR'd:
  "EOG Resources, Inc.
   [(49.768518% x 4/5) plus (35.185186% x 75%)] = .84953704 .66203704"
Correct transcription: operating_interest_text=".84953704" (the FIRST
decimal), net_revenue_interest_text=".66203704" (the SECOND decimal). The
bracketed formula is the NET REVENUE calculation — NEVER put it in
operating_interest_text. If only one decimal is printed after a formula,
that decimal is the NET REVENUE interest; put the formula AND the decimal in
net_revenue_interest_text and leave operating_interest_text as the working
interest only if it is separately printed. The working interest is always
>= the net revenue interest for a leased company.

=== LEASES ===
For each "The Land is subject to the following described oil and gas lease"
block (there may be more than one), extract: lease_date, recording_info
(e.g. "Volume 170, Page 827, Real Records"), lessor, lessee, land_covered
(acreage description), interest_covered, primary_term, royalty,
shut_in_royalty, pooling, pugh_clause, continuous_development,
depth_limitations. Leave any field null with confidence < 0.4 if not stated.

=== REQUIREMENTS / COMMENTS ===
Transcribe any outstanding title requirements or analyst comments as separate
list entries.

=== PREDICTED UNIT COVERAGE ===
You will be told a target unit name. Given the tract's legal description,
judge whether this tract plausibly corresponds to that unit:
  LIKELY_COVERS, LIKELY_DOES_NOT_COVER, or UNCERTAIN (use UNCERTAIN often —
  legal descriptions are usually survey/abstract-based, not unit-name based,
  so direct name matching will frequently be inconclusive even for tracts
  that do cover the unit). This is advisory only for human triage.

=== CONFIDENCE ===
1.0 = read directly from text, unambiguous. 0.7 = inferred from context.
0.4 = damaged/ambiguous text. <0.4 = set value to null.
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

_PARTY_INTEREST_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "party": {"type": "string"},
        "fraction_text": {"type": "string"},
        "confidence": {"type": "number"},
        "provenance": {"type": "string"},
    },
    "required": ["party", "fraction_text", "confidence"],
}

_WORKING_INTEREST_ROW_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "company": {"type": "string"},
        "operating_interest_text": {"type": "string"},
        "net_revenue_interest_text": {"type": "string"},
        "confidence": {"type": "number"},
        "provenance": {"type": "string"},
    },
    "required": ["company", "operating_interest_text", "net_revenue_interest_text", "confidence"],
}

_LEASE_BLOCK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        field: _FIELD_SCHEMA
        for field in (
            "lease_identifier", "lease_date", "recording_info", "lessor", "lessee",
            "land_covered", "interest_covered", "primary_term", "royalty",
            "shut_in_royalty", "pooling", "pugh_clause", "continuous_development",
            "depth_limitations",
        )
    },
}

# Dedicated lease-schedule tool: a SECOND, bounded call that extracts ONLY the
# lease-analysis schedule (every lease block) — no mineral/WI tables — so a
# dense opinion (e.g. Cox: 20+ leases) never truncates the main extraction.
_LEASE_SCHEDULE_TOOL: dict[str, Any] = {
    "name": "extract_lease_schedule",
    "description": "Extract EVERY oil & gas lease listed in a title opinion's lease-analysis section.",
    "input_schema": {
        "type": "object",
        "properties": {"leases": {"type": "array", "items": _LEASE_BLOCK_SCHEMA}},
        "required": ["leases"],
        "additionalProperties": False,
    },
}

_LEASE_SCHEDULE_SYSTEM = """\
You are an oil and gas title analyst. From the OCR text of a title opinion,
extract EVERY lease in the lease-analysis / lease-schedule section — there are
usually many (10-30), often numbered ("Lease No. 1", "1.", "Tract 1 Lease").
Return ONLY a call to the `extract_lease_schedule` tool with one entry per lease.

For each lease transcribe, exactly as printed (never compute):
  lease_identifier (the lease number/label if given), lessor, lessee, lease_date,
  recording_info (volume/page or instrument no.), land_covered, interest_covered
  (the mineral interest/fraction the lease covers, e.g. "1/2 mineral interest"),
  primary_term, royalty, shut_in_royalty, pooling, pugh_clause,
  continuous_development, depth_limitations.
Leave a field null with confidence < 0.4 if not stated. Do NOT skip leases; if the
schedule lists 20 leases, return 20 entries. Provide a short `provenance` quote per
value where practical.
"""

_TRACT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "tract_legal_description": _FIELD_SCHEMA,
        "tract_gross_acres": _FIELD_SCHEMA,
        "certification_date": _FIELD_SCHEMA,
        "letter_date": _FIELD_SCHEMA,
        "surface_owners": {"type": "array", "items": _PARTY_INTEREST_SCHEMA},
        "mineral_owners": {"type": "array", "items": _PARTY_INTEREST_SCHEMA},
        "royalty_owners": {"type": "array", "items": _PARTY_INTEREST_SCHEMA},
        "overriding_royalty_owners": {"type": "array", "items": _PARTY_INTEREST_SCHEMA},
        "working_interest_table": {"type": "array", "items": _WORKING_INTEREST_ROW_SCHEMA},
        "leases": {"type": "array", "items": _LEASE_BLOCK_SCHEMA},
        "requirements": {"type": "array", "items": _FIELD_SCHEMA},
        "comments": {"type": "array", "items": _FIELD_SCHEMA},
        "predicted_unit_coverage": {
            "type": "object",
            "properties": {
                "value": {
                    "type": "string",
                    "enum": ["LIKELY_COVERS", "LIKELY_DOES_NOT_COVER", "UNCERTAIN"],
                },
                "confidence": {"type": "number"},
                "provenance": {"type": "string"},
            },
            "required": ["value", "confidence"],
        },
    },
}

_TOOL_DEFINITION: dict[str, Any] = {
    "name": "extract_title_opinion",
    "description": "Extract structured tract/ownership/lease data from an oil & gas title opinion.",
    "input_schema": {
        "type": "object",
        "properties": {
            "tracts": {"type": "array", "items": _TRACT_SCHEMA},
        },
        "required": ["tracts"],
        "additionalProperties": False,
    },
}


def _build_user_prompt(file_number: str, ocr_text: str, target_unit_name: str) -> str:
    lines = [
        f"TITLE OPINION FILE NUMBER: {file_number}",
        f"TARGET UNIT NAME (for predicted_unit_coverage): {target_unit_name}",
        "",
        "=== OCR TEXT ===",
        ocr_text[:MAX_OCR_CHARS],
        "=== END OCR TEXT ===",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# API call with retry
# ---------------------------------------------------------------------------

def _call_claude(
    file_number: str,
    source_pdf_path: str,
    ocr_text: str,
    target_unit_name: str,
    model: str,
) -> TitleOpinionExtraction:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise LLMConfigError(
            "ANTHROPIC_API_KEY is not set. Export the variable before running TO extraction."
        )

    import anthropic  # noqa: PLC0415 — lazy import; anthropic is optional

    client = anthropic.Anthropic(api_key=api_key)
    user_prompt = _build_user_prompt(file_number, ocr_text, target_unit_name)
    last_exc: Exception | None = None

    for attempt in range(MAX_RETRIES):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=16000,
                system=_SYSTEM_PROMPT,
                tools=[_TOOL_DEFINITION],
                tool_choice={"type": "tool", "name": "extract_title_opinion"},
                messages=[{"role": "user", "content": user_prompt}],
            )
            return _parse_response(file_number, source_pdf_path, response, model)
        except anthropic.RateLimitError as exc:
            last_exc = exc
            delay = RETRY_BASE_DELAY * (2 ** attempt)
            logger.warning(
                "Rate limit (attempt %d/%d) for %s — sleeping %.1fs",
                attempt + 1, MAX_RETRIES, file_number, delay,
            )
            time.sleep(delay)
        except anthropic.APITimeoutError as exc:
            last_exc = exc
            logger.warning("Timeout (attempt %d/%d) for %s", attempt + 1, MAX_RETRIES, file_number)
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_BASE_DELAY)

    raise last_exc or RuntimeError("TO extraction call failed after all retries")


def _field(data: dict[str, Any] | None) -> LLMFieldResult:
    data = data or {}
    return LLMFieldResult(
        value=data.get("value") or None,
        confidence=float(data.get("confidence", 0.0)),
        provenance=data.get("provenance"),
    )


def _parse_response(
    file_number: str,
    source_pdf_path: str,
    response: Any,
    model: str,
) -> TitleOpinionExtraction:
    usage = response.usage
    prompt_tokens = getattr(usage, "input_tokens", 0)
    completion_tokens = getattr(usage, "output_tokens", 0)

    if getattr(response, "stop_reason", None) == "max_tokens":
        return TitleOpinionExtraction(
            file_number=file_number,
            source_pdf_path=source_pdf_path,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            error=(
                "LLM response truncated at max_tokens — the title opinion's structured "
                "output was cut off mid-generation. Likely cause: too many tracts/leases "
                "for the configured output budget. Needs review, not a silent empty result."
            ),
        )

    tool_block = next(
        (b for b in response.content if getattr(b, "type", None) == "tool_use"), None
    )
    if not tool_block:
        return TitleOpinionExtraction(
            file_number=file_number,
            source_pdf_path=source_pdf_path,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            error="No tool_use block in API response.",
        )

    data = tool_block.input or {}
    try:
        tracts = []
        for t in data.get("tracts") or []:
            tracts.append(
                TOTract(
                    tract_legal_description=_field(t.get("tract_legal_description")),
                    certification_date=_field(t.get("certification_date")),
                    letter_date=_field(t.get("letter_date")),
                    surface_owners=[TOPartyInterest(**p) for p in t.get("surface_owners") or []],
                    mineral_owners=[TOPartyInterest(**p) for p in t.get("mineral_owners") or []],
                    royalty_owners=[TOPartyInterest(**p) for p in t.get("royalty_owners") or []],
                    overriding_royalty_owners=[
                        TOPartyInterest(**p) for p in t.get("overriding_royalty_owners") or []
                    ],
                    working_interest_table=[
                        TOWorkingInterestRow(**w) for w in t.get("working_interest_table") or []
                    ],
                    leases=[
                        TOLeaseBlock(**{k: _field(v) for k, v in lease.items()})
                        for lease in t.get("leases") or []
                    ],
                    requirements=[_field(r) for r in t.get("requirements") or []],
                    comments=[_field(c) for c in t.get("comments") or []],
                    predicted_unit_coverage=_field(t.get("predicted_unit_coverage")),
                )
            )
        return TitleOpinionExtraction(
            file_number=file_number,
            source_pdf_path=source_pdf_path,
            tracts=tracts,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
    except Exception as exc:
        return TitleOpinionExtraction(
            file_number=file_number,
            source_pdf_path=source_pdf_path,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            error=f"Response parse error: {exc}",
        )


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _cache_filename(file_number: str, model: str) -> str:
    safe_id = file_number.replace("/", "_").replace(":", "_").replace(" ", "_")
    model_tag = model[:20].replace("/", "_")
    return f"{safe_id}_{model_tag}_{DD_TO_CACHE_SCHEMA_VERSION}_to.json"


def _load_cache(
    file_number: str, model: str, cache_dir: str | Path
) -> TitleOpinionExtraction | None:
    path = Path(cache_dir) / _cache_filename(file_number, model)
    if not path.exists():
        return None
    try:
        return TitleOpinionExtraction.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_cache(
    file_number: str,
    model: str,
    result: TitleOpinionExtraction,
    cache_dir: str | Path,
) -> None:
    try:
        cache_path = Path(cache_dir)
        cache_path.mkdir(parents=True, exist_ok=True)
        (cache_path / _cache_filename(file_number, model)).write_text(
            result.model_dump_json(indent=2), encoding="utf-8"
        )
    except Exception as exc:
        logger.warning("Could not write TO cache for %s: %s", file_number, exc)
