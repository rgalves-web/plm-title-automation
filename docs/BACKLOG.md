# BACKLOG

## Atualização de 11/09/2026 — Training Suite

- Resolvido no Case File: sessões interrompidas fecham em `finally`; custo de
  cada resposta recebida é registrado antes do dispatch. Queda abrupta do SO ou
  ausência de usage do provedor ainda exige reconciliação.
- Resolvido: presença isolada de posição/grafo/corte não produz mais `final`.
  População inteira e revisão registrada, mais aceite do snapshot, são exigidos.
- Pendente: revisão/aprovação das 61 candidatas, reconciliação semântica dos
  fragmentos restantes, inspeção de mídia e eventual avaliação com modelos reais.
  Inventário integral e comandos: `docs/TRAINING_SUITE_INTEGRACAO.md`.
- Fichas antigas da unit que representam grupos precisam de cobertura explícita
  por `population::member` antes de um novo aceite técnico do VS3. Não migrar
  automaticamente a interpretação de grupos por heurística de nomes.

O backlog anterior abaixo é preservado como histórico; as duas correções acima
substituem seus apontamentos abertos correspondentes.

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
| 8 | **L1 has no `plat` category.** The Bowen cold re-drop put `PLAT.TIF` in `reference_workbook` (conf 0.95) — the only miss in 13. Josh B's corpus carries `PLAT.PDF` in most lease folders, so the same document type currently lands in a category that feeds the wrong destination. | **L1 taxonomy** — a `plat` category with its own `feeds`, or an explicit ruling that a plat is a title document. | It did not change the Josh B brief (a plat is never a fetch item), and adding a category mid-PR would invalidate the whole vision cache. |
| 9 | **Lease disposition is document-level, not field-level.** The system says `instrument_of_record` as soon as it reads the lease; the gabarito's list is finer — `0220953-008/-010/-011` have the lease but no individual royalty, and `0221055-002` has two copies whose OCR failed. Those are FIELD gaps in a lease that is present. | **The next PR** — the brief must be able to say "the instrument is here, the royalty is not", which means dispositions carry per-term evidence, not just per-document. | The round still closes: those cells are blanks that today have no owner, so this is the next thing that moves invariant 18 from "the gate passes" to "the gate is complete". |
| 10 | The Bowen First Supplemental has **no certification sentence at all**; the date the delivered package used (10/18/2008) is the runsheet through-date recited under DOCUMENTS EXAMINED. The system now offers it as a `candidate` requiring a human verdict. | If this shape recurs across examiners, the candidate rule belongs in L2 as a named, ranked basis — not in `title_opinion.py`. | One document proves a pattern of one. Promote it to knowledge when a second opinion does the same thing. |
- ~~run_loop sem retry/backoff para erros transitorios da API~~ RESOLVIDO 24/08: dois 529 seguidos bloquearam a ordem do operador (processar P1); `_create_com_retry` no loop.py, backoff exponencial, 5 tentativas, so 429/5xx/529.
- Projeção do ship sem lote: write_cell/record_blank 1 célula por chamada — aplicar o conserto F3 (gravar em lote) à projeção. Alavanca nº1 do CP3 §6.
- Projeção com memória em delta (dump completo de 318 campos + mapa do template a cada sessão custa ~metade da projeção). Alavanca nº2 do CP3 §6.
- `minorh ship --continuar`: retomar do ledger salvo por turno em vez de re-projetar do zero após queda/teto. Alavanca nº3 do CP3 §6.
- Driver de replay: gravar a prova de quarentena em finally (hoje um crash no comando pula o registro da sonda — a proteção fica, o registro não).
- Projecao pode introduzir escape HTML no valor (&amp; onde a memoria tem &): 2-3 celulas no replay 2, ausente na memoria, nasce na sessao de projecao. A auditoria de 100% pega (o trecho citado nao sustenta o escape) — mas vale um teste de regressao quando a auditoria rodar no corpus real.
- Casefile/triagem relista TODOS os pendentes a cada turno (~1.400 nomes): com Sonnet o teto de $3 rendeu só 145 rótulos no smoke E7 (02/09). Fatiar a lista em lotes por sessão (mesma lição F1 do continuar).
- Casefile/sessao: queda no meio do run_loop (5x 529 em 02/09) deixa model_sessions aberta e o custo dos turnos pagos fora de cost_entries (fica só no progresso jsonl). Fechar sessão e contabilizar em finally.
- Casefile/triagem com nome ambíguo (2 conteúdos, mesmo logical) rotula ambos os hashes com o mesmo rótulo — aceitável no VS1, mas o VS3 deve rotular por conteúdo.
- VS3/verificacao: a transcricao independente do Exhibit A (paginas 3-4 da DPU) nao devolve o bloco 0220604/001-018 em nenhuma das duas passadas (sub-serie/ditto na tabela?). 18 leases ficam evidencia_insuficiente — investigar recorte por regiao/zoom da pagina antes da proxima rodada.
- VS3: sessao interrompida por credito nao registra intervencao de data de corte; a retomada (posicoes/grafo ausentes => re-roda) cobre, mas vale fechar sessao+custo em finally (item ja aberto) e registrar pergunta automatica.
- Approval dialog ticks all six sources by default, including RRC; default should be local only.
