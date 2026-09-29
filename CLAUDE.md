# CLAUDE.md — plm-title-automation

Claude Code loads this file automatically at the start of every session. It is **durable project context**, not a task list. The task for the current session comes from the session prompt. If this file conflicts with your assumptions, this file wins; if it conflicts with the actual code, the code wins and you must flag the drift.

---

## What this repo is

A local-first title-automation system for Purple Land Management (PLM) land work, serving **Project Emirates** (engagement `BKV122TX`; client BKV Corp.; EOG Resources Inc. as Seller; ~300 units, Montague/Cooke Counties, Texas; per-unit **DDR** Excel deliverable).

**The governing architecture is LLM-first — decided by the operator on 2026-08-23. Read `docs/ARQUITETURA_GOVERNANTE.md` first; it prevails over every other document, including this one's history.** In one line: no title decision in Python; AI judges, a second AI head verifies, Python only opens files, renders pages, calls models, saves bytes — and protects bytes (see "the pen" below).

Current direction (2026-09-11): **Case File per Unit in PostgreSQL** (`src/casefile/`).
Training Suite implementation, coverage, activation and limitations:
`docs/TRAINING_SUITE_INTEGRACAO.md`. No VS3 acceptance or VS4 authorization is implied.

The generations coexist in the tree:

- **`src/casefile`** — current direction. Versioned methodology, sessions, claims, research and reviews flow through the database to the API/dashboard.
- **`src/minorh` + `src/examinador`** — frozen previous path, retained for replays and plumbing imports. Legacy knowledge base in `knowledge_okf/`; Case File reads both local/global versions and writes candidates without overwriting it.
- **`src/dd`, `src/knowledge`, MOR (`src/*.py` root)** — the frozen deterministic generations. History, regression fixtures, and a source of *plumbing* to extract (file copying, template reading, md5). They never re-enter the decision path.
- `docs/WORKBENCH_STATUS.md` is owned by Code and records the current baseline; assessments (`FULL_SYSTEM_ASSESSMENT.md`, `SYSTEM_ASSESSMENT.md`) are historical.

Historical repair order: `docs/CODE_INSTRUCTIONS_CONSERTO_DEFINITIVO.md`.
Later Case File decisions and the current Training Suite request govern their
own scope; the still-applicable operator checkpoints are preserved.

---

## Invariants — never violate

**Universal (both generations, every session):**

1. **Ground every claim in a real file.** Never invent module, function, or test names. If you have not opened it, say so rather than guessing.
2. **No title decision in Python.** If code chooses, compares a title fact, computes an interest, filters by judgment, or approves content — it does not enter. Judgment belongs to the Examinador; verification of judgment belongs to a second AI head of an independent family, never to an `if`.
3. **The pen protects bytes; that is not judgment.** Mandatory pen properties: refuse writes to template formula cells (formula-set hash before/after every save); write-roots declared before writing; frozen delivered packages; gabarito quarantine during replays; md5 round-trip on kits; cost accounting with a hard per-unit budget cap (`MINORH_TETO_UNIT_USD`, default 25 — on hitting it the system stops and reports, never silently continues). A refused write returns a named error to the model, which redecides; it never becomes a silent blank.
4. **Tests stay green.** Run the full suite before changing anything and after. Never reduce coverage. New behavior requires a new test — of plumbing, never of judgment: no test in this repo asserts a title conclusion.
5. **Branch-only.** Never commit to `main`/`master`. Work on a branch, keep a rollback point, never force-push.
6. **Source traceability is mandatory.** Every value that reaches a deliverable carries a literal citation (document, page, quote, confidence) or the cell is blank with a named reason and owner. Blank-declared beats plausible. No cell ships unaudited; a cell that fails audit twice ships blank with the reason in the trail.
7. **No silent learning.** An operator answer in PERGUNTAS.md becomes an OKF precedent through the tool, visibly. Never mutate config, prompts, or fichas as a side effect of a chat message.
8. **Client data never leaves the machine.** Client PDFs, XREFs, Project Logs, DDRs, transcripts, and any EOG/PLM/BKV material are confidential. Never commit them, never push them to any remote, never send whole documents to an API when an extracted snippet suffices, never paste them into external services.
9. **FILES/ is read-only; corpus is read in place** from the original zips (`corpus_reader`/`examinador.corpus`); extraction only into scratch at the moment of use; a standing duplicate of client files is a violation.
10. **Delivered packages are frozen.** Nothing writes a byte inside `<UNIT>/SUBMISSION PLM/` of a shipped unit. `minorh publicar` refuses an existing target.
11. **The answer sheet is quarantined.** A replay that reads the gabarito is not a replay and its score is not evidence. Quarantine is by identity (gabarito/hand-delivered kit outside the round's write-roots), not by folder-name pattern — the kit the round itself is assembling under `_minorh/ship/kit/` is readable.
12. **Absence is never inferred from ignorance.** "Unplaced" can never support "missing". A document found at the county is never reported as "could not be located" — the note states only the remaining deficiency.
13. **A finding that does not change the current target's deliverable does not become a commit.** It becomes a line in `docs/BACKLOG.md`.
14. **Every report ships with its artefacts.** Populations declared before measuring; a coverage number that rises must be explained document by document before it becomes a baseline (the 11/08 resolver lesson: plausible-and-wrong "confirmations" from identity-by-string-containment).

**Frozen-generation only (when a session must touch `src/dd`/`src/knowledge`/MOR for fixtures or plumbing extraction):** the old rules of that generation apply there (closed exclusion vocabulary, `fractions.Fraction` arithmetic, gates on bytes re-read from disk). Do not "modernize" them; do not re-wire them into the decision path.

---

## Domain glossary (so you don't misread the data)

- **DDR** — Due Diligence Report (Excel deliverable, per unit).
- **TO** — Title Opinion PDF. Original + Supplements over the **same legal description** → the **most recent by certification date controls**; earlier ones are superseded. Use the ownership certification "as of" date, not the date printed at the top.
- **DPU / DOU** — Declaration of Pooled Unit / Designation of Unit. Exhibit "A" lists the unit's leases (the perimeter authority); Exhibit "C" the tracts. Cross-checking DPU × both XREF sheets × Lease & Mineral Schedule is mandatory at kickoff; divergences are findings.
- **XREF** — Lease-to-Well-and-Contract cross-reference workbook (two sheets; filter both).
- **WI / NRI** — Working Interest / Net Revenue Interest. Leasehold (TO-derived) vs wellbore (Well List) mismatch is often JOA non-consent uplift, not a defect.
- **Supplemental title** — chain from the controlling cert date to present, seller-affecting and **of record** only.
- **Recording references** are multi-county strings (Cooke + Montague dual-recording exists); Cooke reception numbers restart each year — always pair with the year.

## Known traps (from real runs)

- A supplement can state ownership as a prose formula; the newest opinion is never silently skipped for parseability — that is a blocking finding for the model to raise.
- Non-recorded internal paperwork must never reach the Runsheet; of-record is a classification duty with quoted recording evidence.
- Garbled OCR acreage (`19.2` vs `119.2`) propagates into denominators — acreage needs a legible source or a declared blank.
- Template sample data has leaked into deliverables before; the artefact is born template-minus-sample and every cell needs provenance.
- A filename is a weak prior, never a rule (folder T0141070 held T0141066's bytes).
- The blue-formula-cell rule is the most repeated client rule on Slack; the pen enforces it (invariant 3).

Surface-title preparation (2026-09-12): see `docs/CIBOLA_PREPARACAO.md`. Explicit per-case planning profile; downstream surface collection/examination/export remains pending. Do not apply Emirates defaults to a configured surface case.
