---
concept: padrao montagem pacote phase i
type: regra-cliente
sources:
- ordem CODE_INSTRUCTIONS_ETAPA_H (28/08/2026) — lições da rodada manual da Webb B
- docs/PLM_PHASE1_SUBMISSION_SPEC.md
- '[[sop-10-formato-e-empacotamento]]'
links: []
unit: ''
confidence: ''
---

## H3 — Montagem do pacote (os detalhes que o spec não escreve)

- `Title Documents/` = todo instrumento do runsheet, nome `book.page.pdf` **puro** — sem sufixo descritivo, sem TIF. Instrumento de suporte a defeito (fora do runsheet) pode ficar, também book.page puro, declarado na checklist com a conta exata ("45 of the 46").
- `Title Opinions/` = uma pasta `Unit Tract N` para **cada** trato da Unit Designation, INCLUSIVE VAZIAS — vazio declarado na checklist vence pasta inexistente. Uma opinião é copiada para TODOS os tratos que cobre. Opinião que não correlaciona NÃO ganha pasta inventada ("Tract correlation pending" é não-conforme): fica solta na raiz com a razão declarada na checklist.
- **Ler a opinião antes de aceitar o nome do arquivo.** O "AMIS 50 AC" da Webb B era o T0141078 e cobria 11 parcelas em seis tratos — o nome escondia; a leitura derrubou um pedido aberto havia 18 dias. A correlação trato↔opinião sai do TEXTO da opinião (lista de tracts + anotações de lease na capa), nunca do nome do arquivo.
- `Unit Designations/` book.page puro. `PLM Report/` só o DDR.
- Checklist: Notes **em inglês** (houve regressão em português), declarando lacuna com NÚMERO ("45 of the 46", "9 tract folders empty") — nunca advérbio vago.
- Limpeza é movimento para `_LIXO/`, nunca deleção; a árvore final é varrida contra o spec pasta a pasta antes do ping de submissão.
