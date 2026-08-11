# CLAUDE.md — plm-title-automation

Claude Code loads this file automatically at the start of every session. It is **durable project context**, not a task list. The task for the current session comes from the session prompt. If this file conflicts with your assumptions, this file wins; if it conflicts with the actual code, the code wins and you must flag the drift.

---

## What this repo is

A local-first title-automation system for Purple Land Management (PLM) land work. Two pipelines:

- **MOR** — Master Ownership Report / runsheet. Mature, tested.
- **DD** — Due Diligence. Produces a per-unit **DDR** (Excel deliverable) for **Project Emirates** (engagement `BKV122TX`; EOG Resources Inc. as Seller; ~300 units, Montague County, Texas).

The authoritative description of current state is **`docs/WORKBENCH_STATUS.md`** plus the specs in **`docs/`**. Read them before reasoning about architecture. `FULL_SYSTEM_ASSESSMENT.md` and `SYSTEM_ASSESSMENT.md` are historical references (their golden rules remain binding; their "current state" sections do not).

---

## Invariants — never violate

1. **Ground every claim in a real file.** Never invent module, function, or test names. If you have not opened it, say so rather than guessing.
2. **Deterministic math stays deterministic.** WI/NRI and all interest arithmetic run through `fractions.Fraction` in code — never through LLM free-text reasoning. The LLM may supply field *values*; it may never compute, estimate, or "sanity-guess" the totals.
3. **Tests stay green.** Run the full suite before changing anything and after. Never reduce coverage. New behavior requires a new test.
4. **Branch-only.** Never commit to `main`/`master`. Work on a branch, keep a rollback point, never force-push.
5. **Source traceability is mandatory.** Every value that reaches a deliverable carries filename + path + page/cell + extraction method. No orphan values.
6. **No silent learning.** A user correction is task-local until explicitly promoted. Never mutate config, prompts, Golden Set, or code as a side effect of a chat message.
7. **Client data never leaves the machine.** Client PDFs, XREFs, Project Logs, DDRs, transcripts, and any EOG/PLM material are confidential. Never commit them, never push them to any remote, never send whole documents to an API when an extracted snippet suffices, never paste them into external services.
8. **Least-invasive fix first.** Prefer a config / rule / Golden-Set / memory fix over a code change. Change code only when nothing safer solves it, and only with a regression test. Never change source and declare success without running tests.
9. **AI decides what a document is and what it says — always with a citation** (file, page, quote, confidence). **Code proves** (`fractions.Fraction`, the gates, round-trip). No value enters a case or deliverable without evidence.
10. **A filename is a weak prior, never a rule.** No triage SKIP without a first-page peek or strong metadata (duplicate hash / non-document type).
11. **Every recorded reason (blank, SKIP, unplaced, waiver) comes from the closed vocabulary** (`knowledge/rules/exclusion_reasons.yaml`). Free prose in a reason field is a writing error.
12. **No L2 rule classifies without content having been read.** L2 delimits and supplies vocabulary; the AI reads and proposes; the human arbitrates by risk tier.
13. **`knowledge/` never contains a unit fact** in `global`/`project`/`ontology`/`taxonomy`/`rules` (enforced by a linter in the suite). Unit facts live in `data/units/`.
14. **Every lesson has a fixture** (two-part format); a fixture without bytes on disk is a counted SKIP, never a silent pass.
15. **The single source of truth for case files is the `evidence_ledger`**; `catalog.yaml`/`graph.yaml` are projections of it.

---

## Domain glossary (so you don't misread the data)

- **DDR** — Due Diligence Report (Excel deliverable, per unit).
- **MOR** — Master Ownership Report / runsheet.
- **TO** — Title Opinion PDF. Original + Supplements over the **same legal description** → the **most recent by certification date controls**; earlier ones are superseded.
- **DPU / DOU** — Declaration of Pooled Unit / Designation of Unit. Exhibit A lists the leases in the unit. Cross-checking the DPU against the XREF lease list is a **mandatory** step the pipeline must support, not skip.
- **XREF** — Lease-to-Well-and-Contract cross-reference workbook.
- **WI / NRI** — Working Interest / Net Revenue Interest.
- **Supplemental title** — chain of title from the controlling opinion's cert date to present, limited to instruments **affecting the Seller's (EOG's) interest** and **of record** only.
- **Controlling cert date** — certification date of the controlling opinion; the scope floor for supplemental review.

---

## Known traps (from real runs — see assessment §6)

- A supplement can state ownership as a prose formula the fraction parser can't resolve; the system may **silently fall back to an older opinion**. Surface this, never hide it.
- Compound formulas like `62.5% x 7/8 less (…)` are currently **dropped, not computed**.
- **Non-recorded internal memos** can pass the supplemental filter and pollute the Runsheet.
- **Garbled OCR acreage** (e.g. `19.2` vs `119.2`) propagates into the WI/NRI denominator with only a soft flag.
- **Template / sample-row data has leaked into deliverables before.** A clean-output check is required on every write.

---

## Product direction (context — NOT the current session's task)

Long-term goal: an **LLM operating layer** over these pipelines — one conversational, local-first interface that plans work, calls the existing deterministic functions **as tools**, tracks a persistent workspace, and learns from approved corrections behind explicit approval gates. Existing deterministic code is **wrapped as tools, never replaced**. Rollout is phased; each phase must leave the system usable. The session prompt states which phase/scope is in play. **Do not start later-phase work unprompted** (no learning loop, self-modification, or vector search unless the session prompt asks for it).
