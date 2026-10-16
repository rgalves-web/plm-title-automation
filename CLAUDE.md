# CLAUDE.md — plm-title-automation

Claude Code loads this file automatically at the start of every session. It is **durable project context**, not a task list. The task for the current session comes from the session prompt. If this file conflicts with your assumptions, this file wins; if it conflicts with the actual code, the code wins and you must flag the drift.

---

## What this repo is

Current transport override (2026-10-16): Renato requested deletion of model API keys and operation through Claude Code and Codex terminals, with publication to his existing GitHub repository. Read `docs/EXECUCAO_TERMINAL.md`. Operational cases use `profile.execution_backend=terminal`; `PLM_API_DISABLED=1` prevents SDK fallback. CLI subscription receipts are separate from historical API charges. Login/limits can block work; never infer unlimited or free usage. Earlier API implementation notes below are historical for billing and migration, not authorization to restore API keys.

A local-first title-automation system for Purple Land Management (PLM) land work, serving **Project Emirates** (engagement `BKV122TX`; client BKV Corp.; EOG Resources Inc. as Seller; ~300 units, Montague/Cooke Counties, Texas; per-unit **DDR** Excel deliverable).

**The governing architecture is LLM-first — decided by the operator on 2026-08-23. Read `docs/ARQUITETURA_GOVERNANTE.md` first; it prevails over every other document, including this one's history.** In one line: no title decision in Python; AI judges, a second AI head verifies, Python only opens files, renders pages, calls models, saves bytes — and protects bytes (see "the pen" below).

Current operation (2026-10-12): **visual workbench + four API workers + Case File per Unit in PostgreSQL** (`src/casefile/`). Read `docs/OPERACAO_VISUAL.md` for the current entry point, migration and actual acceptance state. Renato authorized the four-case Cibola pilot, local snippets/pages, through date 2026-10-11, Claude production and OpenAI verification, up to USD 50 per tract. His later instruction caps **all remaining development API use at USD 20 additional in total**, enforced through shared reservations. Unknown charges from earlier requests remain unresolved; never infer zero usage or resume those cases without receipts. Derek's local exemplar was explicitly confirmed for Cibola. Purchases, external communication, PREP transmission and submission still require their specific authorization. The previous Streamlit UI is removed and the historical Minorh/webapp launchers are retired. Frozen modules remain regression fixtures, outside the current runtime dependencies.
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

## Domain language

The domain glossary lives in `GLOSSARY.md` at the repo root. Use its terms; architectural decisions live in `docs/adr/`.

## Known traps (from real runs)

- A supplement can state ownership as a prose formula; the newest opinion is never silently skipped for parseability — that is a blocking finding for the model to raise.
- Non-recorded internal paperwork must never reach the Runsheet; of-record is a classification duty with quoted recording evidence.
- Garbled OCR acreage (`19.2` vs `119.2`) propagates into denominators — acreage needs a legible source or a declared blank.
- Template sample data has leaked into deliverables before; the artefact is born template-minus-sample and every cell needs provenance.
- A filename is a weak prior, never a rule (folder T0141070 held T0141066's bytes).
- The blue-formula-cell rule is the most repeated client rule on Slack; the pen enforces it (invariant 3).

Surface-title preparation history (2026-09-12): see `docs/CIBOLA_PREPARACAO.md`. The current visual runtime enables collection, examination, independent review and writing under the explicit Cibola profile. The historical CLI restriction remains outside that runtime. Do not apply Emirates defaults to a configured surface case.

## Cibola — mandatory submission protocol adopted 2026-10-01

Before any Cibola work, read `../Land Cibola Surface Titles/AGENTS.md` and `../Land Cibola Surface Titles/00_Governanca/PROTOCOLO_SUBMISSAO_PLM.md`. This is Renato's explicit instruction to persist and apply the supplied Marc Reyes protocol: Derek's exact entry examples, a real PREP review of each submitted report, final Spell Check, and SME treatment of technical questions, with evidence tied to the reviewed version. Never mark these done from a training card or a self-generated checklist. Read `../Land Cibola Surface Titles/00_Governanca/README.md` for the implementation record and limitations. Renato authorized uploads of work in progress on 2026-10-01, identified as WORKING DRAFT with version and gaps. Every partial or final submission must comply with the protocol. Project Log remains read-only. Training configuration does not remove surface execution restrictions or approve title.


## Agent skills

### Issue tracker

Issues live as local markdown files under `.scratch/<feature>/`. See `docs/agents/issue-tracker.md`.

### Triage labels

Default vocabulary, recorded as a `Status:` line in each issue file: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: root `GLOSSARY.md` + `docs/adr/`. See `docs/agents/domain.md`.
