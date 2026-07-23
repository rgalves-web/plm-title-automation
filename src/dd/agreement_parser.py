"""Extract agreement fields from RECORDED contract instruments (Agreements tab).

The Agreements tab's card blocks were shipping "[PENDING - document not in
file]" for contracts whose recorded instruments sit ON DISK in the unit's
project folder. Standing rule: PENDING is only valid when the document genuinely
is not on disk — if the file exists, the pipeline reads it or fails loudly.

The LLM transcribes field VALUES with the page they came from; it computes
nothing. A field the instrument does not state stays None and the caller records
reason `stated_nowhere_in_instrument` — an assignment has no tax-partnership
article, and saying so (with the instrument in hand) is the finished answer,
not a gap.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from src.llm_extractor import LLMFieldResult
from src.utils import get_logger

logger = get_logger(__name__)

DD_AGMT_CACHE_SCHEMA_VERSION = "dd_agmt_v1"
# A recorded partial assignment with its exhibit runs ~59k OCR chars; take it whole.
MAX_OCR_CHARS = 60000
DEFAULT_MODEL = "claude-haiku-4-5-20251001"
LLM_MODEL_ENV = "PLM_LLM_MODEL"
MAX_RETRIES = 3
RETRY_BASE_DELAY = 4.0

# The Agreements card's labeled rows. Everything the tab asks for, nothing else.
AGREEMENT_FIELDS = (
    "grantor", "counterparty", "effective_date", "instrument_form",
    "contract_area", "depth_limitation", "non_consent_penalties",
    "preferential_right_to_purchase", "maintenance_of_uniform_interest",
    "tax_partnership", "area_of_mutual_interest", "unusual_provisions",
    "amendments", "recording_info",
)


class AgreementExtraction(BaseModel):
    source_path: str = ""
    contract_no: str = ""
    model: str = ""
    error: str | None = None
    grantor: LLMFieldResult = Field(default_factory=LLMFieldResult)
    counterparty: LLMFieldResult = Field(default_factory=LLMFieldResult)
    effective_date: LLMFieldResult = Field(default_factory=LLMFieldResult)
    instrument_form: LLMFieldResult = Field(default_factory=LLMFieldResult)
    contract_area: LLMFieldResult = Field(default_factory=LLMFieldResult)
    depth_limitation: LLMFieldResult = Field(default_factory=LLMFieldResult)
    non_consent_penalties: LLMFieldResult = Field(default_factory=LLMFieldResult)
    preferential_right_to_purchase: LLMFieldResult = Field(default_factory=LLMFieldResult)
    maintenance_of_uniform_interest: LLMFieldResult = Field(default_factory=LLMFieldResult)
    tax_partnership: LLMFieldResult = Field(default_factory=LLMFieldResult)
    area_of_mutual_interest: LLMFieldResult = Field(default_factory=LLMFieldResult)
    unusual_provisions: LLMFieldResult = Field(default_factory=LLMFieldResult)
    amendments: LLMFieldResult = Field(default_factory=LLMFieldResult)
    recording_info: LLMFieldResult = Field(default_factory=LLMFieldResult)


_SYSTEM_PROMPT = """You are transcribing fields from a RECORDED oil & gas contract instrument \
(assignment, partial assignment, farmout) for a due-diligence report. The OCR text of the \
recorded instrument follows, with pages separated by form-feed characters.

Rules — these are absolute:
- Transcribe ONLY what the instrument states. Never infer, summarize from outside knowledge, \
or guess. If the instrument does not address a field (e.g. an assignment with no tax-partnership \
article), return null for that field — a null is a correct answer.
- For every non-null field, provenance must cite the page ("p.2") the value appears on. \
Page 1 is before the first form-feed, page 2 after it, and so on.
- recording_info is the county recording stamp (volume/page or instrument number) ON the document.
- effective_date is the instrument's own effective/dated date, not the recording date.
- Values are concise clauses in the instrument's own words, at most ~200 characters each."""

_TOOL_DEFINITION = {
    "name": "extract_agreement",
    "description": "Record the fields the recorded instrument states.",
    "input_schema": {
        "type": "object",
        "properties": {
            name: {
                "type": ["object", "null"],
                "properties": {
                    "value": {"type": ["string", "null"]},
                    "confidence": {"type": "number"},
                    "provenance": {"type": ["string", "null"],
                                   "description": "page cite, e.g. 'p.2'"},
                },
            }
            for name in AGREEMENT_FIELDS
        },
    },
}


def _field(data: Any) -> LLMFieldResult:
    if data is None:
        return LLMFieldResult(value=None, confidence=0.0)
    if not isinstance(data, dict):
        text = str(data).strip()
        return LLMFieldResult(value=text or None, confidence=0.0,
                              provenance="model returned a bare value; confidence unstated")
    return LLMFieldResult(value=(data.get("value") or None),
                          confidence=float(data.get("confidence") or 0.0),
                          provenance=data.get("provenance"))


def _cache_path(contract_no: str, doc_stem: str, model: str, cache_dir: Path) -> Path:
    import hashlib
    digest = hashlib.md5(f"{contract_no}|{doc_stem}".encode()).hexdigest()[:10]
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in f"{contract_no}_{doc_stem}")[:60]
    return cache_dir / f"{safe}_{digest}_{model[:24]}_{DD_AGMT_CACHE_SCHEMA_VERSION}.json"


def parse_agreement(
    ocr_text: str,
    contract_no: str,
    source_path: str | Path,
    cache_dir: str | Path | None = None,
) -> AgreementExtraction:
    """One recorded instrument -> its stated agreement fields."""
    model = os.environ.get(LLM_MODEL_ENV, DEFAULT_MODEL)
    doc_stem = Path(source_path).stem
    if cache_dir:
        cache_dir = Path(cache_dir)
        cached = _cache_path(contract_no, doc_stem, model, cache_dir)
        if cached.exists():
            try:
                return AgreementExtraction(**json.loads(cached.read_text(encoding="utf-8")))
            except Exception:
                pass

    if len(ocr_text) > MAX_OCR_CHARS:
        logger.warning("Agreement %s: OCR %s chars truncated to %s — later pages unread.",
                       contract_no, f"{len(ocr_text):,}", f"{MAX_OCR_CHARS:,}")

    import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return AgreementExtraction(source_path=str(source_path), contract_no=contract_no,
                                   model=model, error="ANTHROPIC_API_KEY is not set.")
    client = anthropic.Anthropic(api_key=api_key)
    prompt = (f"CONTRACT NO: {contract_no}\nINSTRUMENT FILE: {Path(source_path).name}\n\n"
              f"=== OCR TEXT ===\n{ocr_text[:MAX_OCR_CHARS]}\n=== END OCR TEXT ===")
    last_exc: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            response = client.messages.create(
                model=model, max_tokens=4000, system=_SYSTEM_PROMPT,
                tools=[_TOOL_DEFINITION],
                tool_choice={"type": "tool", "name": "extract_agreement"},
                messages=[{"role": "user", "content": prompt}],
            )
            data = next((b.input for b in response.content if b.type == "tool_use"), {})
            result = AgreementExtraction(
                source_path=str(source_path), contract_no=contract_no, model=model,
                **{name: _field(data.get(name)) for name in AGREEMENT_FIELDS})
            if cache_dir:
                cache_dir.mkdir(parents=True, exist_ok=True)
                _cache_path(contract_no, doc_stem, model, cache_dir).write_text(
                    json.dumps(result.model_dump(mode="json")), encoding="utf-8")
            return result
        except anthropic.RateLimitError as exc:
            last_exc = exc
            time.sleep(RETRY_BASE_DELAY * (2 ** attempt))
        except Exception as exc:  # noqa: BLE001 — one instrument must not kill the batch
            logger.warning("Agreement extraction failed for %s: %s", contract_no, exc)
            return AgreementExtraction(source_path=str(source_path), contract_no=contract_no,
                                       model=model, error=str(exc))
    return AgreementExtraction(source_path=str(source_path), contract_no=contract_no,
                               model=model, error=str(last_exc))


@dataclass
class MergedAgreement:
    """A contract's fields merged across its primary instrument + amendments."""
    contract_no: str
    fields: dict[str, LLMFieldResult] = field(default_factory=dict)
    sources: list[str] = field(default_factory=list)

    def value(self, name: str) -> str | None:
        f = self.fields.get(name)
        return f.value if f else None


def merge_instrument_extractions(
    contract_no: str,
    primary: AgreementExtraction,
    amendments: list[AgreementExtraction] = (),
) -> MergedAgreement:
    """Deterministic merge: the primary instrument's statement wins per field;
    an amendment only FILLS a field the primary leaves silent — except
    `amendments`, which is the amendment instrument's own description."""
    merged = MergedAgreement(contract_no=contract_no,
                             sources=[Path(primary.source_path).name])
    for name in AGREEMENT_FIELDS:
        merged.fields[name] = getattr(primary, name)
    for amendment in amendments:
        merged.sources.append(Path(amendment.source_path).name)
        for name in AGREEMENT_FIELDS:
            current = merged.fields.get(name)
            candidate = getattr(amendment, name)
            if name == "amendments":
                # The amendment's self-description supersedes the primary's silence.
                if candidate and candidate.value:
                    merged.fields[name] = candidate
            elif (current is None or not current.value) and candidate and candidate.value:
                merged.fields[name] = candidate
    return merged
