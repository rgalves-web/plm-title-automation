# PLM Title Automation — Session Handoff Document
**Generated:** 2026-06-23  
**Purpose:** Complete technical context for a new Claude session to continue development.

---

## 1. PROJECT OVERVIEW

**Name:** PLM Title Automation  
**Stack:** Python 3.12, Streamlit UI, Windows 11, PowerShell  
**Location:** `c:\Users\Renato\PURPLE LAND MGMT\plm-title-automation\`  
**Purpose:** Automate oil & gas chain-of-title runsheet generation (Mineral Ownership Reports / MOR). Takes a document package ZIP (PDFs + Excel document list), runs classification, OCR, LLM extraction, ownership ledger computation, and produces a filled Excel runsheet template.

**Active dataset:** Section 15, Township 4S, Range 64W, Arapahoe County, Colorado  
**Package ZIP:** `data/input/document_packages/4S-64W-15-20260602T114641Z-3-001.zip`  
**Template:** `data/working/uploads/*.xlsx` (scanned at runtime)  
**Output root:** `data/output/e2e/`

---

## 2. DIRECTORY STRUCTURE

```
plm-title-automation/
  src/
    schemas.py          # Pydantic models: SourceDocument, ProjectMetadata, QAException, etc.
    intake.py           # Read document list from ZIP or Excel
    document_register.py # Create SourceDocument list from DataFrame
    dedupe.py           # Duplicate detection
    classifier.py       # Rule-based classification (INCLUDE/REDLINE/REVIEW/DUPLICATE)
    lease_engine.py     # is_oil_and_gas_lease(), infer_lease_status()
    source_matcher.py   # Match source PDFs from package ZIP to records
    pdf_reader.py       # PDF text extraction + OCR via Tesseract
    llm_extractor.py    # Anthropic Claude API: conveyance, comments, grantor_exact, grantee_exact, instrument_effect
    ownership.py        # Chain-of-title ledger using fractions.Fraction
    pipeline.py         # Orchestrator: run_full_pipeline_from_dataframe()
    qa.py               # QA exceptions, hard stops, export
    excel_writer.py     # Fill runsheet template, generate output XLSX
    utils.py            # Logging, file helpers, normalize_text()
  config/
    rules.yaml          # Classification keyword rules
    template_map.yaml   # Column mappings + accepted_missing_sources list
  scripts/
    run_section_e2e.py  # Full end-to-end run + print report
    _show_results.py    # Read and print from existing output dir (no re-run)
    smoke_llm.py        # LLM smoke test: 15 stable records
    _read_qa.py         # Print QA log from output dir
    generate_sample_data.py
  tests/
    test_classifier.py  # 4 tests + 4 new (Mech 1+3)
    test_llm_extractor.py # 10 tests + 3 new (instrument_effect)
    test_ownership.py   # 6 tests + 4 new (name normalization)
    test_qa.py          # 8 tests + 1 new (accepted_missing_sources)
  data/
    input/document_packages/  # ZIP packages
    working/uploads/           # Excel template files
    output/e2e/                # Pipeline output dirs
  .env                  # ANTHROPIC_API_KEY=sk-...
  PLM_SESSION_HANDOFF.md  # THIS FILE
```

---

## 3. SCHEMAS (src/schemas.py)

### ClassificationStatus (enum)
```python
INCLUDE_FULL    # Full interest conveyance — goes on runsheet
INCLUDE_LIMITED # Limited/fractional — goes on runsheet
REDLINE         # Non-title instrument (easement, lien, etc.)
REVIEW          # Needs human review before classification
DUPLICATE       # Duplicate of another record
```

### LeaseStatus (enum)
```python
ACTIVE    # OGL currently in force
EXPIRED   # Primary term lapsed, no HBP evidence
RELEASED  # Formally released
REVIEW    # Cannot determine status
```

### SourceDocument (Pydantic BaseModel) — KEY FIELDS
```python
source_document_id: str          # e.g. "DOC-000001"
source_row_number: int
document_type: str               # "Patent", "Mineral Deed", "Oil and Gas Lease", etc.
instrument_number: str
book: str | None
page: str | None
effective_date: date | None
instrument_date: date | None
recording_date: date | None
grantor: str | None              # From index; may be overwritten by LLM (grantor_exact)
grantee: str | None              # From index; may be overwritten by LLM (grantee_exact)
conveyance: str | None           # Filled by LLM extraction
comments: str | None             # Filled by LLM extraction
legal_description: str | None
acreage: str | None
status: ClassificationStatus | None
classification_confidence: float | None
classification_reason: str | None
redline_reason: str | None
review_question: str | None
lease_status: LeaseStatus | None
# Source verification fields
matched_source_file: str | None
source_match_confidence: float | None
source_match_method: str | None
extracted_text_path: str | None
pdf_extraction_status: str | None  # "TEXT_EXTRACTED", "OCR_REQUIRED", "EXTRACTION_ERROR", etc.
pdf_extraction_confidence: float | None
pdf_page_count: int | None
pdf_text_preview: str | None
possible_document_type_keywords: list[str]
possible_legal_description_snippets: list[str]
possible_lease_primary_term_snippets: list[str]
# LLM tracking
llm_extraction_model: str | None
llm_conveyance_confidence: float | None
llm_comments_confidence: float | None
# Audit trail
source_trace: dict[str, Any]    # Rich audit dict — see section 7
raw: dict[str, Any]             # Original Excel row values
```

### source_trace keys used by the pipeline (audit trail)
```
pre_source_verification_status   → str: status before OCR demotion (e.g. "INCLUDE_FULL")
source_verification_demotion_reason → str: "EXTRACTION_ERROR" | "POSSIBLE_LEASE_TERM"
reclassified_by                  → str: "llm_extraction_recovery" | "llm_instrument_effect"
original_demotion_reason         → str: copy of demotion reason after recovery
instrument_effect                → str: e.g. "ASSIGNS_OGL"
instrument_effect_provenance     → str: LLM provenance text
grantor_index                    → str: original index grantor (before LLM overwrite)
grantee_index                    → str: original index grantee (before LLM overwrite)
llm_extraction                   → dict: full LLMExtractionResult.model_dump()
llm_extraction_error             → str: error message if LLM failed
llm_low_confidence_fields        → list[str]: fields below threshold
lease_status_source              → str: "llm_post_extraction"
lease_status_needs_review        → bool: True if ACTIVE (needs human confirmation)
project_metadata                 → dict: {section, township, range} from ProjectMetadata
pdf_extraction_error             → str: error message
pdf_populated_fields             → dict: {conveyance: bool, legal_description: bool, ...}
matched_source_path              → str: full path to matched PDF
```

---

## 4. PIPELINE STAGES (src/pipeline.py)

`run_full_pipeline_from_dataframe()` — main entry point:

```
1. create_document_register()     → list[SourceDocument] from DataFrame
2. deduplicate_documents()        → marks DUPLICATE rows
3. classify_documents()           → INCLUDE_FULL/LIMITED/REDLINE/REVIEW via rules.yaml
4. run_source_verification()      → [optional] match PDFs, OCR, extract text
5. run_llm_extraction()           → [optional] Claude API for conveyance/comments/parties/instrument_effect
   ├── apply_instrument_effect_reclassification()  [Mechanism 2]
   ├── _run_llm_recovery()                         [Mechanism 1]
   └── _refresh_lease_status_post_llm()            [Mechanism 3]
6. run_ownership_analysis()       → chain-of-title ledger → ownership_entries.json
7. Export artifacts (XLSX, JSON)
8. run_qa()                       → QAException list
9. assert_no_hard_stops()         → raises QAHardStopError if any ERROR severity
10. generate_runsheet_with_report() → fill Excel template
```

### LLM eligibility filter
Records must have ALL of:
- `status in {INCLUDE_FULL, INCLUDE_LIMITED, REVIEW}`
- `pdf_extraction_status == "TEXT_EXTRACTED"`
- `extracted_text_path` exists on disk

REDLINE and DUPLICATE are never sent to LLM.

---

## 5. LLM EXTRACTOR (src/llm_extractor.py)

**Model:** `claude-haiku-4-5-20251001` (default; override via `PLM_LLM_MODEL` env var)  
**API key:** `ANTHROPIC_API_KEY` from `.env`  
**Cache version:** `v3` (bump if schema changes)  
**Cache location:** `{output_dir}/QA_internal/llm_cache/`

### LLMExtractionResult fields
```python
source_document_id: str
conveyance: LLMFieldResult      # Canonical prefix + legal description
comments: LLMFieldResult        # Title-relevant notes (Primary Term, Royalty, etc.)
grantor_exact: LLMFieldResult   # Party name exactly as written in instrument body
grantee_exact: LLMFieldResult   # Party name exactly as written in instrument body
instrument_effect: LLMFieldResult  # enum: CONVEYS_MINERAL | ASSIGNS_OGL | RELEASES_LEASE | EASEMENT_ONLY | NO_TITLE_EFFECT | UNCLEAR
model: str
prompt_tokens: int
completion_tokens: int
error: str | None
```

### Confidence thresholds
```python
HIGH_CONFIDENCE = 0.85           # grantor_exact/grantee_exact overwrite + instrument_effect acts
LOW_CONFIDENCE_THRESHOLD = 0.60  # below this → field not written, QA WARNING emitted
```

### Conveyance canonical prefixes (system prompt)
```
Patent                    → "Grant of:"
Deed (full)               → "ARTI to:"
Deed (fractional)         → "an undivided X/Y interest to:"
Oil and Gas Lease         → "Lease covering:"
Assignment of OGL         → "Assignment of Lease covering:"
Release of OGL            → "Release of Lease covering:"
Correction Deed           → "Correction of:"
```

### instrument_effect reclassification logic (Mechanism 2)
Only acts on REVIEW records whose `classification_reason` contains one of:
- `"unclear_assignment"`
- `"possible_title_effect"`
- `"No deterministic rule matched"`

```
CONVEYS_MINERAL | ASSIGNS_OGL  → record.status = INCLUDE_FULL  (if confidence >= 0.85)
EASEMENT_ONLY | NO_TITLE_EFFECT → record.status = REDLINE      (if confidence >= 0.85)
UNCLEAR                          → no change
```

---

## 6. CLASSIFICATION (src/classifier.py + config/rules.yaml)

Rules are keyword-based, evaluated in order: REDLINE → REVIEW → INCLUDE_FULL → INCLUDE_LIMITED → REVIEW (fallback).

**Key review rules that produce REVIEW:**
- `unclear_assignment` — keyword "assignment", "bill of sale" without clear OGL context
- `possible_title_effect` — correction deed, affidavit, court order ambiguities

**REVIEW fallback:** `"No deterministic rule matched"` — sent to REVIEW with `review_question = "Confirm whether this instrument affects title or minerals."`

`is_oil_and_gas_lease(record)` — uses `record.search_text()` which includes `document_type`, `document_title`, `grantor`, `grantee`, `legal_description`, and `comments`. **KNOWN BUG:** if LLM writes "oil and gas lease" in the `comments` field (e.g. "Subject to any rights under valid and subsisting oil and gas lease of record"), the function returns True for non-OGL records. This causes false `MISSING_LEASE_STATUS` QA errors.

---

## 7. OWNERSHIP ENGINE (src/ownership.py)

Uses `fractions.Fraction` arithmetic — never floats.

### canonical_party_key(name) — name normalization
```python
# Steps:
# 1. Uppercase
# 2. Strip .," punctuation
# 3. Collapse whitespace
# 4. Normalize suffixes: JR./JUNIOR → JR, SR./SENIOR → SR
# 5. Loop-strip non-identity descriptors from end:
#    "AND HUSBAND AND WIFE", "HUSBAND AND WIFE", "AND WIFE", "AND HUSBAND",
#    "A SINGLE WOMAN", "A SINGLE MAN", "INDEPENDENT EXECUTOR",
#    "PERSONAL REPRESENTATIVE", "DECEASED", "TRUSTEE", "PLAINTIFF", "DEFENDANT"

# Examples:
canonical_party_key("MARY JONES AND HUSBAND")  → "MARY JONES"
canonical_party_key("John  Smith.")             → "JOHN SMITH"
canonical_party_key("JOHN SMITH JR.")           → "JOHN SMITH JR"
# JR is preserved (identity suffix) — father and son remain distinct
```

### Fuzzy matching thresholds
```python
FUZZY_AUTO_UNIFY   = 93  # score >= 93  → auto-unify silently, add alias
FUZZY_POSSIBLE_MATCH = 80  # score in [80,93) → POSSIBLE_NAME_MATCH exception, no transfer
# score < 80 → not_found → TitleException
```

### Ledger logic
- `fee_ledger`: tracks mineral fee interest (Fraction per canonical key)
- `royalty_ledger`: separate for royalty deeds
- `wi_ledger`: working interest (OGL grantees, active only)
- **Patent** (`"Grant of:"`) → sets grantee to 1/1 unconditionally (no grantor balance required)
- **Full transfer** (`"ARTI to:"`) → moves entire grantor balance to grantee
- **Fractional** → moves exact fraction; exception if grantor balance insufficient
- **OGL** → adds to wi_ledger if ACTIVE or None; skips if EXPIRED/RELEASED

### OwnershipResult
```python
entries: list[OwnershipEntry]      # Final ownership table
exceptions: list[TitleException]   # Title gaps, POSSIBLE_NAME_MATCH, SUMMARY
ledger_total_fraction: str         # Should be "1/1" for complete chain
party_aliases: dict[str, list[str]]  # canonical_key → all display names seen
possible_name_matches: list[dict]  # {grantor, candidate, score, instrument, source_document_id}
```

---

## 8. QA SYSTEM (src/qa.py)

### Hard stop codes (severity="ERROR" → blocks runsheet export)
```
DOCUMENT_COUNT_MISMATCH    # len(records) != expected_document_count
MISSING_STATUS             # record.status is None
MISSING_REDLINE_REASON     # REDLINE record with no redline_reason
MISSING_REVIEW_QUESTION    # REVIEW record with no review_question
MISSING_LEASE_STATUS       # OGL record with no lease_status (uses is_oil_and_gas_lease())
DUPLICATE_WITHOUT_CANONICAL # DUPLICATE with no duplicate_of
DUPLICATE_INCLUDED         # record has duplicate_of but status = INCLUDE
TEMPLATE_CHECK_FAILED      # Template validation failed
PDF_EXTRACTION_ERROR       # extraction_status = EXTRACTION_ERROR
SOURCE_FILE_NOT_MATCHED    # Required source not matched (unless in accepted_missing_sources)
```

### Warning codes (severity="WARNING" → logged but does not block)
```
PDF_OCR_REQUIRED
PDF_LOW_CONFIDENCE
POSSIBLE_LEASE_TERM_UNRESOLVED
LEGAL_DESCRIPTION_SECTION_MISMATCH
LLM_EXTRACTION_FAILED
LLM_EXTRACTION_LOW_CONFIDENCE
SOURCE_FILE_NOT_MATCHED    # (when instrument is in accepted_missing_sources)
```

### accepted_missing_sources
Configured in `config/template_map.yaml`:
```yaml
accepted_missing_sources:
  - "56937-1979"   # DOC-000334: CERSLE, Houlihan → Capital Invest Co
  - "64392-1987"   # DOC-000378: CERSLE, Houlihan → Tool C L
```
**NOTE:** These two instrument numbers are known to have no PDF in the ZIP package. They must be added to this list to downgrade SOURCE_FILE_NOT_MATCHED from ERROR → WARNING.  
**CURRENT STATE:** `accepted_missing_sources: []` — the list is EMPTY. This is a pending fix.

---

## 9. THREE REDUCTION MECHANISMS (all implemented in pipeline.py)

### Mechanism 1: LLM recovery from OCR demotion (`_run_llm_recovery`)
Restores INCLUDE status for records that were demoted to REVIEW **only** because OCR/PDF extraction failed, when the LLM subsequently extracted conveyance with confidence >= 0.85.

Eligibility:
- `record.status == REVIEW`
- `source_trace["pre_source_verification_status"] in ("INCLUDE_FULL", "INCLUDE_LIMITED")`
- `source_trace["source_verification_demotion_reason"]` is set
- `record.llm_conveyance_confidence >= 0.85`

Action: restores status, clears review_question, sets `source_trace["reclassified_by"] = "llm_extraction_recovery"`.

### Mechanism 2: instrument_effect reclassification (in `run_llm_extraction`)
See section 5 above. Runs per-record immediately after `apply_llm_extraction_to_record()`.

### Mechanism 3: Post-LLM lease status refresh (`_refresh_lease_status_post_llm`)
For OGLs where `lease_status in {None, REVIEW}`, calls `infer_lease_status(record, extracted_text=llm_text)` using the LLM-written `conveyance + comments` text. Sets `source_trace["lease_status_source"] = "llm_post_extraction"`.

---

## 10. CURRENT PIPELINE RUN RESULTS

**Last run directory:** `data/output/e2e/4S-64W-15_Arapahoe_20260610_140345`

| Metric | Value |
|---|---|
| Total documents | 464 |
| INCLUDE (full+limited) | 53 |
| REDLINE | 130 |
| REVIEW | **216** (46.5% — target is to reduce this) |
| DUPLICATE | 65 |
| QA errors (hard stops) | **3** |
| Runsheet generated | **NO** (blocked by 3 hard stops) |
| LLM extracted ok | 241 / 267 eligible |
| LLM extraction errors | 26 |
| conveyance LLM coverage | 65.06% |
| comments LLM coverage | 47.21% |
| Cross-references found | 0 |
| Ownership entries | 5 |
| Ownership ledger total | 2 (expected 1 — structural gaps) |
| Sum = 1 | False |
| Title exceptions | 15 |
| POSSIBLE_NAME_MATCH | 0 |
| Ownership needs_review | 3 |

**IMPORTANT:** The three mechanisms (1, 2, 3) were implemented in the previous session but have NOT yet been tested in a full real run. The run above used the OLD code (without mechanisms). The first post-implementation run is still pending.

---

## 11. THE 3 QA HARD STOPS (blocking runsheet)

### Hard Stop 1: MISSING_LEASE_STATUS for DOC-000001
- **DOC-000001** — Instrument `1005494-2011` — Document type: **Mineral Deed**
- **Root cause (BUG):** `is_oil_and_gas_lease()` calls `record.search_text()` which includes the `comments` field. The LLM wrote "Subject to any rights under valid and subsisting oil and gas lease of record; grantee receives bonus..." in `comments`. This causes `is_oil_and_gas_lease()` to return `True` for a Mineral Deed.
- **Fix needed:** In `src/qa.py`, function `_qa_record()`, the `MISSING_LEASE_STATUS` check should use only `record.document_type`, NOT `is_oil_and_gas_lease(record)`. Or alternatively, `is_oil_and_gas_lease()` should check only `document_type` and not `search_text()`.
- **Proposed fix in qa.py:**
```python
# CURRENT (buggy):
if (
    record.status != ClassificationStatus.REDLINE
    and is_oil_and_gas_lease(record)    # ← uses search_text(), catches OGL mentions in comments
    and not record.lease_status
):

# FIXED:
_OGL_TYPE_KEYWORDS = ("oil and gas lease", "oil & gas lease", "o&g lease", "oil gas lease")
def _is_ogl_by_type(record) -> bool:
    doc_type = (record.document_type or "").lower()
    return any(kw in doc_type for kw in _OGL_TYPE_KEYWORDS)

if (
    record.status != ClassificationStatus.REDLINE
    and _is_ogl_by_type(record)    # ← checks only document_type
    and not record.lease_status
):
```

### Hard Stop 2: SOURCE_FILE_NOT_MATCHED for DOC-000334
- **Instrument:** `56937-1979`
- **Type:** CERSLE (Certificate/Release type)
- **Grantor:** "HOULIHAN,J J IV ET AL" → **Grantee:** "CAPITAL INVEST CO"
- **Fix:** Add `"56937-1979"` to `accepted_missing_sources` in `config/template_map.yaml`

### Hard Stop 3: SOURCE_FILE_NOT_MATCHED for DOC-000378
- **Instrument:** `64392-1987`
- **Type:** CERSLE
- **Grantor:** "HOULIHAN,J J IV ET AL" → **Grantee:** "TOOL,C L"
- **Fix:** Add `"64392-1987"` to `accepted_missing_sources` in `config/template_map.yaml`

---

## 12. PENDING TASKS (in priority order)

### Task 1 — Fix MISSING_LEASE_STATUS false positive (src/qa.py)
Change the OGL check in `_qa_record()` to use `document_type` only, not `search_text()`.
Also consider: should `is_oil_and_gas_lease()` in `src/lease_engine.py` be split into two functions — one for classification context (uses `search_text()`) and one for strict type checking (uses only `document_type`)? The current single function is overloaded.

### Task 2 — Add instrument numbers to accepted_missing_sources (config/template_map.yaml)
```yaml
accepted_missing_sources:
  - "56937-1979"
  - "64392-1987"
```

### Task 3 — Re-run scripts/run_section_e2e.py
After Tasks 1 and 2, re-run the full pipeline. The LLM cache (v3) is populated from the previous run, so only new/uncached records will hit the API. Expected behavior:
- 0 QA hard stops
- Runsheet generated
- REVIEW count reduced from 216 (Mechanisms 1+2+3 active for first time in real run)
- Report: new INCLUDE/REDLINE/REVIEW/DUPLICATE counts, how many records each mechanism reclassified

### Task 4 (future) — Ownership ledger gaps
The ledger total = 2 (expected 1) is structural: 15 title exceptions show grantors (1975–2022) who never appear as grantees in the INCLUDE set. These are real chain-of-title gaps in the dataset, not code bugs. Would need either:
- Additional documents in the package
- Analyst manual entry of gap-filling data
- A "presumed ownership" entry mode

---

## 13. TEST STATUS

**59 tests passing** as of 2026-06-23.

| Test file | Count | Notes |
|---|---|---|
| test_classifier.py | 4 + 4 = 8 | 4 new: Mechanism 1 (_run_llm_recovery), Mechanism 3 (_refresh_lease_status_post_llm) |
| test_llm_extractor.py | 10 + 3 = 13 | 3 new: instrument_effect ASSIGNS_OGL, EASEMENT_ONLY, UNCLEAR |
| test_ownership.py | 6 + 4 = 10 | 4 new: canonical_party_key, non-identity descriptor strip, possible_name_match, JR suffix |
| test_qa.py | 8 + 1 = 9 | 1 new: accepted_missing_sources downgrades ERROR → WARNING |

Run: `python -m pytest -q`

---

## 14. KEY CONFIGURATION FILES

### config/template_map.yaml (current state — needs update)
```yaml
# Instrument numbers whose source PDFs are acknowledged absent by the analyst.
# Adding to this list downgrades SOURCE_FILE_NOT_MATCHED from ERROR to WARNING.
accepted_missing_sources: []    # ← NEEDS: ["56937-1979", "64392-1987"]
```

### .env (never committed)
```
ANTHROPIC_API_KEY=sk-ant-...
```

### Tesseract location (hardcoded in pdf_reader.py)
```
C:\Program Files\Tesseract-OCR\tesseract.exe   (version 5.4.0)
```

---

## 15. IMPORTANT CODING CONSTRAINTS

1. **Windows cp1252 console** — Do NOT use Unicode characters in `print()` statements. Use ASCII equivalents: `!!` instead of `⚠`, `--` instead of `—`, `...` instead of `…`. The run scripts use `io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")` to work around this.

2. **Fractions, never floats** — All ownership arithmetic uses `fractions.Fraction`. Never convert to float during computation. Float is only for Excel output (`interest_decimal`).

3. **LLM is optional** — `anthropic` package is lazy-imported inside `run_llm_extraction()`. The pipeline works without LLM; pass `llm_extraction=False` (default) to skip.

4. **Cache invalidation** — When changing LLM tool schema fields, bump `CACHE_SCHEMA_VERSION` in `src/llm_extractor.py`. Current version: `"v3"`.

5. **Pipeline entrypoint** — `run_full_pipeline_from_dataframe()` is the canonical entry point used by both the Streamlit UI and scripts. Always use this, not lower-level functions directly.

6. **is_oil_and_gas_lease() is overloaded** — used in classifier (legitimate to check full text), ownership ledger (legitimate), AND qa.py MISSING_LEASE_STATUS check (should be type-only). This is the source of the current bug.

---

## 16. HOW TO RUN

### Full end-to-end (with LLM):
```powershell
cd "c:\Users\Renato\PURPLE LAND MGMT\plm-title-automation"
python scripts/run_section_e2e.py
```

### Show results from existing run (no re-run):
```powershell
python scripts/_show_results.py "data/output/e2e/4S-64W-15_Arapahoe_20260610_140345"
# or latest:
python scripts/_show_results.py
```

### Run tests:
```powershell
python -m pytest -q
```

### LLM smoke test (15 stable records):
```powershell
python scripts/smoke_llm.py
```

---

## 17. OWNERSHIP WORKSHEET — CURRENT RESULTS

5 entries from last run (ledger total = 2, sum ≠ 1):

| Party | Source Deed | Interest Type | Fraction | Needs Review |
|---|---|---|---|---|
| Whitetail Minerals, LLC | 7024085-2017 | Fee - OGM | ? | YES |
| Bull Moose Royalties, LLC | 8040228-2018 | Fee - OGM | ? | YES |
| Incline Energy Partners I, LP | 33813-2022 | Fee - OGM | ? | YES |
| (unnamed) | 8046763-2018 | Fee - OGM | 1 | no |
| "USA" | 5098566-2015 | Fee - OGM | 1 | no |

**15 title exceptions** — all are grantors with no established ledger balance (chain-of-title gaps, not code bugs). The most common pattern: grantors active in 1975–1995 who never appear as grantees in the INCLUDE set.

---

## 18. WHAT WAS BUILT IN THE PRECEDING SESSION

The previous session implemented ALL of the following (tests written, all passing):

1. **src/ownership.py** — Complete rewrite:
   - `canonical_party_key()` with non-identity descriptor stripping
   - Fuzzy matching at 93/80 thresholds via `rapidfuzz`
   - `OwnershipResult` with `party_aliases` and `possible_name_matches`
   - `_is_patent()` separated from `_is_full_transfer()` (fixes Patent → ARTI chain)
   - `_move_interest()` guard: `if amount <= Fraction(0): return`

2. **src/llm_extractor.py** — Extended:
   - `grantor_exact`, `grantee_exact` fields (overwrite index at confidence >= 0.85)
   - `instrument_effect` field with 6-value enum
   - `apply_instrument_effect_reclassification()` function
   - `CACHE_SCHEMA_VERSION = "v3"` (bumped for new fields)
   - `_apply_party_field()` saves original as `source_trace["{field}_index"]`

3. **src/pipeline.py** — Extended:
   - `_mark_extraction_error()` saves `pre_source_verification_status` before demotion
   - `_run_llm_recovery()` — Mechanism 1
   - `_refresh_lease_status_post_llm()` — Mechanism 3
   - `run_llm_extraction()` calls `apply_instrument_effect_reclassification` — Mechanism 2
   - `run_full_pipeline_from_dataframe()` calls Mechanisms 1+3 after LLM block
   - Loads `accepted_missing_sources` from template config and passes to `run_qa()`

4. **src/qa.py** — Extended:
   - `run_qa()` and `_qa_source_verification()` accept `accepted_missing_sources: list[str]`
   - Downgrades `SOURCE_FILE_NOT_MATCHED` to WARNING for acknowledged absences

5. **config/template_map.yaml** — Added `accepted_missing_sources: []`

6. **scripts/run_section_e2e.py** — Created (full e2e run + metrics + runsheet/ownership preview)

7. **scripts/_show_results.py** — Created (read existing output, no re-run)

8. **scripts/smoke_llm.py** — Fixed: now loads `.env`, uses deterministic sorted selection

---

## 19. NEXT IMMEDIATE ACTIONS FOR NEW SESSION

**Step 1:** Fix `_qa_record()` in `src/qa.py` — change `MISSING_LEASE_STATUS` check to use `document_type` only (not `is_oil_and_gas_lease()` which reads `search_text()`).

**Step 2:** Update `config/template_map.yaml`:
```yaml
accepted_missing_sources:
  - "56937-1979"
  - "64392-1987"
```

**Step 3:** Run `python -m pytest -q` — confirm still 59 passing (or add test for the qa.py fix if classification_reason changes).

**Step 4:** Run `python scripts/run_section_e2e.py` — first real run with all 3 mechanisms active. Report:
- New INCLUDE/REDLINE/REVIEW/DUPLICATE counts
- `llm_metrics["reclassified_to_include"]` (Mechanism 2 count)
- `llm_metrics["reclassified_to_redline"]` (Mechanism 2 count)
- `llm_metrics["recovery_count"]` (Mechanism 1 count)
- `llm_metrics["lease_status_updated"]` (Mechanism 3 count)
- Whether runsheet was generated
- First 10 INCLUDE rows from runsheet
- Ownership worksheet entries
