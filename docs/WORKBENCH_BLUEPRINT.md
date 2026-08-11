# MINORH WORKBENCH — Flow & Usability Blueprint
**Date:** 2026-07-23 · **Target repo:** `plm-title-automation` (branch `maxwell-lessons-hardening`) · **Companion:** `minorh-workbench-prototype.html` (navigable prototype, Minorh brand)

> Purpose: turn a pile of correct machinery into a system that **knows what to do and how to do it**. This document is the implementation spec for the workflow layer. It assumes the SYSTEM_ASSESSMENT of 2026-07-22 as the ground truth of the current state.

---

## 1. Diagnosis

The repo today is strong on **application knowledge** (how to compute WI/NRI, how to validate cells, how to package a submission) and weak on **form** (what happens next, who does what, where things live). Symptoms, all documented in prior assessments:

- Allowlists are assembled by hand per validation run; a stale `manifest.yaml` produces false `foreign_unit_leakage` (assessment §3.1).
- Classification is filename-regex driven and calibrated to one client's naming (`_TO_NAME_RE`, `_SELLER_*`) — it misclassifies silently on new conventions (§3.2).
- Operational knowledge lives in Claude session memory and markdown ("never search by abstract", "screenshots need visual confirmation") instead of in the system.
- The entry point is code (`run_dd_pipeline_for_unit`) — a new analyst cannot operate it, and even the author must remember invariants (long OCR windows, sidecar rules, FILES read-only).
- There is no persisted, versioned per-unit state: every session reconstructs where the unit stands.

**The thesis of this blueprint:** the domain engine is done enough. What must be built is a thin, opinionated **flow layer** that owns state, sequencing, evidence, and learning — and a UI that makes the flow visible. The engine modules become callees; they stop being the interface.

---

## 2. Design principles (non-negotiable)

1. **The unit is a case.** All state, evidence, decisions and outputs hang off one unit case file. Nothing exists "per session".
2. **The checklist is the method.** The system tells the analyst what to fetch, where, what it looks like, and why — the analyst never memorizes the process.
3. **No ingestion rules.** One drop zone. Content-based classification; the filename is a *hint with a confidence penalty*, never a rule. Every guess shows its evidence; the human confirms or corrects in one click. Nothing is discarded silently — unmatched files land in a visible "unplaced" list with a reason.
4. **Allowlists are derived, never typed.** The allowlist for validation is computed from the evidence ledger (confirmed TOs, contracts, leases) at run time. Kills assessment trap #1 permanently.
5. **Every correction is a lesson.** Human overrides (classification, identity, exclusion) are persisted as scoped rules (unit → project → global) and applied on the next run. Hardcoded regexes are demoted to *seed lessons* in data, not code.
6. **Gates are not optional and not visible as configuration.** Structural gate + source-truth gate always run; the UI shows the two numbers that matter: `0 FAIL`, `0 MISMATCH`. Long OCR runs happen in background — the flow layer owns the scheduling, not the operator's patience.
7. **Blank is a statement.** An empty cell always carries one of three named reasons: document not located / pending third-party definition / fact absent from the record. (Checkpoint lesson #2.)
8. **Existing invariants are inherited unchanged:** FILES read-only; sidecar never a tab; never invent a file; `fractions.Fraction` for math; correct-and-fewer beats plausible-and-wrong.

---

## 3. The Unit Journey — state machine

Six stages, strictly ordered, each with entry/exit conditions. The UI stepper is a projection of this machine; the machine lives in the backend and is valid without any UI.

| # | Stage | Enters when | Exits when | Engine calls |
|---|---|---|---|---|
| 1 | **OPEN** | unit name chosen | manifest built & persisted | `manifest_builder.build_manifest` |
| 2 | **GATHER** | manifest exists | all *blocking* checklist items IN or waived-with-reason | `checklist_builder` (new) |
| 3 | **DROP** | continuous (overlaps 2) | every dropped file confirmed or explicitly unplaced | `intake_router` (wrapped), classifier (new content-first) |
| 4 | **RUN** | evidence sufficient | DDR written · 0 FAIL · 0 MISMATCH (or named unverifiables) | `dd_pipeline`, `ddr_validator`, `source_truth_check` |
| 5 | **REVIEW** | gates green | review queue empty (all verdicts recorded) | `provenance`, verdict store (new) |
| 6 | **SHIP** | review complete | package assembled + manifest written | `submission_packager` |

Stage regressions are allowed and logged (new evidence at REVIEW pushes back to RUN). The current stage, its blocking items, and "next step" phrase are computed properties — this is what the Units board displays.

---

## 4. New subsystems (the actual work)

### 4.1 `src/flow/unit_state.py` — canonical case file
Single YAML/JSON per unit at `data/units/<UNIT>/state.yaml`, versioned (v1, v2… on every mutation, previous versions retained). Contains: manifest snapshot, stage, checklist with statuses, evidence ledger refs, derived allowlist, gate results, verdicts, packaging summary. **This is the persisted manifest the assessment calls for (debt §4)** — re-validation becomes reproducible from this file alone.

### 4.2 `src/flow/evidence_ledger.py`
Append-only ledger of every file that enters the case: `dropped → classified(confidence, evidence_quote, page) → confirmed|corrected|unplaced(reason) → cited_by[cells]`. The ledger is the source for: derived allowlists, the DROP screen, submission packaging inputs, and the audit answer to "where did this number come from".

### 4.3 `src/flow/checklist_builder.py`
Generates the GATHER checklist from the manifest + template requirements. Each item is data, not prose in code:
```yaml
- id: to_T0140319
  kind: title_opinion
  blocking: false            # supplement controls; wanted-not-blocking
  what: "Original title opinion, Brumbaugh 45.62-ac tract"
  looks_like: "PDF, first pages say TITLE OPINION, cert date earlier than 2010-06-01"
  where: ["Drive: lease folder 0220345-001, files starting T-O", "note: folder T0130363 exists but is empty"]
  why: "Latest cert date controls; absence is declared, not blocking"
```
Item templates per `kind` (title_opinion, dpu, lease_folder, county_search, rrc_report, reference_workbook) ship with the product; the manifest instantiates them. County-search items embed the method ("by grantor/grantee name + date window — never by abstract") as rendered guidance.

### 4.4 `src/flow/classifier.py` — content-first classification
Order of evidence: (1) content extraction (first pages text/OCR + LLM label against the *expected checklist items* as candidates), (2) structural cues (zip member layout, xlsx sheet names), (3) filename as weak prior. Output: `(item_id | unplaced, confidence, evidence_quote, page)`. Below a confidence floor, or for any image/screenshot, the row demands visual confirmation (assessment §3.3 made mandatory by flow, not by discipline). Existing regexes (`_TO_NAME_RE` etc.) become *seed hints* loaded from `lessons/seed.yaml`.

### 4.5 `src/flow/lessons.py`
Store: `lessons/<scope>.yaml` with `{rule, kind, scope: unit|project|global, source_event, created}`. Applied at classify/validate/package time. Every human correction in the UI writes one. Review UI for promoting a project lesson to global. The four seed lessons from this engagement: the "TO-separator" rule, screenshot-visual-confirmation, name+date-window county search, JOA-uplift-is-not-a-defect.

### 4.6 `src/flow/verdicts.py`
Per-cell human verdicts (`confirmed | mismatch | waived(reason)`) persisted in the state file, keyed by (tab, cell, value-hash). The next RUN re-applies verdicts whose value hash is unchanged — reviews never repeat. This is the "continue learning from feedback" requirement at cell granularity.

### 4.7 `src/flow/config.py`
One `config.yaml`: tesseract path (with graceful degradation + honest error surfaced in the UI), source roots, OCR window defaults, model settings. Deletes both hardcoded `tesseract_cmd` sites (debt §4).

---

## 5. UI architecture

- **Serve locally:** FastAPI + the single-page front (the prototype's design system: Graphite/Lime, Fraunces once per view, JetBrains Mono for every verifiable number, one primary action per view). `minorh serve` → browser.
- **Screens = prototype screens:** Units board · Unit workspace with 6-stage stepper (Open / Gather / Drop / Run / Review / Ship) · Lessons ledger. The prototype HTML is the visual contract — implement it, don't reinterpret it.
- **Long tasks** (source-truth OCR) run as background jobs with progress streamed to the RUN screen; the operator never chooses a timeout.
- **Streamlit `app.py`:** freeze, keep as fallback during Phase 2, delete in Phase 3.
- All copy in English (client-facing product), sentence case, examiner's voice per brand guidelines: state what was verified and how; no unexplained acronyms.

---

## 6. Migration plan

**Phase 1 — Flow spine (backend only, no UI).** `unit_state`, `evidence_ledger`, `checklist_builder`, `config`. Wrap `run_dd_pipeline_for_unit` so it reads/writes the state file and derives the allowlist from the ledger. Acceptance: re-validating Maxwell v13 from `state.yaml` alone reproduces 0 FAIL / 0 MISMATCH with zero hand-built allowlist.

**Phase 2 — Workbench UI.** FastAPI + the prototype front on top of the spine: board, stepper, drop/classify with confirm-correct, run screen with live gates, review queue with cell trace + verdicts, ship screen with decision log. Acceptance: a person who has never seen the repo takes a fresh unit from OPEN to a packaged submission without reading any documentation.

**Phase 3 — Learning loop.** `classifier` content-first + `lessons` + `verdicts` re-application. Demote filename regexes to seed lessons. Acceptance: reclassifying a file once changes behavior on the next drop; a repeated review shows only cells whose values changed.

**Housekeeping alongside Phase 1:** merge or rebase `maxwell-lessons-hardening` (30 commits ahead — decide now); keep the 494-test suite green at every step; new modules get tests in the same style (`tests/test_flow_*.py`).

---

## 7. What this explicitly does NOT change

The math core, the validators, the packager semantics, the DDR template discipline, and every golden rule in SYSTEM_ASSESSMENT §6. The flow layer sequences and feeds these; it never relaxes them. A matcher is never loosened to make a stage turn green.

---

## 8. Acceptance criteria (the user's words, made testable)

- **"Poucos cliques":** fresh unit → packaged submission in ≤ 12 operator interactions (excluding fetching documents themselves).
- **"Sem regras de ingestão":** any correctly classifiable document is accepted regardless of name; misclassification is visible + correctable in one click; nothing disappears silently.
- **"Didático e visual":** every checklist item renders what/where/looks-like/why; every county-search item renders the method.
- **"Rastreabilidade total":** any cell → source document, page, method, math, and human verdict in ≤ 2 clicks.
- **"Continua aprendendo":** corrections persist as lessons and demonstrably change the next run.
