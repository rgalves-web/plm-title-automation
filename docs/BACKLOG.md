# BACKLOG

Findings that do **not** change the current target's deliverable. Per CLAUDE.md
invariant 17 they do not become commits — they wait here until they do.

**Current target (corrected 2026-08-11): Josh B was delivered by hand** (package
06/08, closed 10/08) and is now the THIRD fixture. The target is split:
**Checkpoint A** — the cold Josh B replay reproducing the written gabarito
(correctness); **Checkpoint B** — the next unit PLM assigns, shipped end to end
by the system (efficiency, and the only honest hours/unit measurement). A
finding earns a commit only if it moves one of those; everything else lands
here.

| # | Finding | Where it belongs | Why not now |
|---|---|---|---|
| ~~1~~ | **CLOSED as data in PR-2.** `Lease Review` term checkers look up a lease's document **by lease number** and do not know a recorded **memorandum** answers for it (Bowen F15/F16/F17/F26, F28/F29/F30 — memos on disk and resolvable, cells still pending). | **OKF F2/F4** — L2 identity/precedence rule + `lease_memorandum —is_of_record_of→ lease` in the graph. Already written into `OKF_MIGRATION_PLAN.md` as phase acceptance. | Bowen is shipped and frozen. Fixing the checker in place would patch a symptom in a delivered unit instead of building the rule as data. |
| 2 | A lease the DDR treats as in-unit but the DPU Exhibit "A" does not name surfaces as a generic unverifiable cell (Bowen Ownership K/L rows 21/22/23/32/34/35/36) instead of a **named perimeter divergence**. | **OKF F3** — S2 SCOPE output. Written into `OKF_MIGRATION_PLAN.md` as phase acceptance. | Same: it is the architecture's job to emit this on its own, before deep OCR — not a Bowen repair. |
| 3 | Citation → file resolution still matches **text** (prefix + abstract + byte-hash) rather than parsing the citation into a **structured identity** and resolving by key (TO = abstract + gross acres + cert date). | **OKF PR-1 fixture → F2/F4** — the fixture locking `A-227 → A-227` / `A-682 → A-682` ships in PR-1; key-based resolution is the definitive form. | Today's fix is correct and tested; the key-based rewrite needs L0 identity keys to exist first. |
| 4 | `data/units/<UNIT>/truth_run*.json` and `_reconciliation_final.json` are ad-hoc analysis artefacts written during the reconciliation, not a designed projection. | **OKF F4 (D2)** — they should be the `catalog.yaml` / `graph.yaml` projections of the ledger, written through the round-trip check. | Works for the reconciliation; replacing it before the ledger is extended would be rework. |
| 5 | The 27 Bowen NRI cells whose ORRI column carries prose remain unverifiable by construction (the identity is not computable from narrative burdens). | **OKF F4** — prose-formula parsing (flow spec §2 rule 6): AI converts the expression, `Fraction` evaluates it. | Bowen is frozen; the capability belongs to the classifier/extraction layer. |
| 6 | The delivered Josh B tree is `JOSH B UNIT/1. Landman Submitted/` — NOT under `SUBMISSION PLM/`, so invariant 16's marker does not protect it. A replay that wrote there would mutate a delivered fixture. | Before the Checkpoint A replay (PR-3): make the frozen set data (config `frozen_paths`) instead of a single hardcoded marker. | PR-2 only READS the corpus, so nothing is at risk yet; the fence must exist before anything replays into that tree. |
| 7 | The delivered folder has grown since the 06/08 package: 67 leases vs 53, 32 title documents vs 19, 4 well files vs 1. The gabarito's counts are a snapshot of build day, not of the folder today. | Checkpoint A must compare against the WRITTEN gabarito, not the live folder, or it will "find more" for the wrong reason. | Recorded now so the replay does not celebrate a difference that is just later work. |
