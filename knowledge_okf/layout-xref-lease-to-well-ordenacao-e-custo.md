---
concept: layout-xref-lease-to-well-ordenacao-e-custo
type: layout
sources:
- 'lease to well and contract xref 06-16-2026 (1).xlsx p.0 (2 abas: Sheet1 65.471
  linhas/328 janelas; Sheet2 54.842 linhas/275 janelas)'
- lease to well and contract xref 06-16-2026 (1).xlsx 1:1 (cabecalho + primeiras linhas)
- lease to well and contract xref 06-16-2026 (1).xlsx 2:1 (cabecalho + primeiras linhas)
- lease to well and contract xref 06-16-2026 (1).xlsx 2:275 (cauda)
links:
- layout-workbooks-bkv122tx-well-list-project-log-e-xref
- veredito-grao-da-aba-ownership-worksheet-uma-linha-por-lease
- custo-search-corpus-em-dump-multiunidade
- escopo-cruzado-quando-xref-e-schedule-nao-estao-no-corpus
unit: ''
confidence: alta para colunas e ordenação; a razão de Sheet2 começar em 0221714 fica
  em aberto
---

## `lease to well and contract xref 06-16-2026 (1).xlsx` — anatomia, ordenação e CUSTO

Detalha a entrada resumida em `layout-workbooks-bkv122tx-well-list-project-log-e-xref`.

### Colunas (IDÊNTICAS nas duas abas) — 26, e **NENHUMA de trato**
`INCLUDE FLAG | LEASE NO | LESSOR | LESSEE | ACTIVE FLAG | RECORD TYPE | RIGHTS HELD | PROPERTY STATUS | LEASE DATE | EFF DATE | EXP DATE | EXT EXP DATE | STATE | COUNTY | WELL OR CONTRACT NB | WELL OR CONTRACT NAME | ACTIVE FLAG | RECORD TYPE | RIGHTS HELD | WELL PROD STATUS | AGMT DATE | EFF DATE | WELL OPERATOR | WELL API | STATE | COUNTY`

Grão da linha = **lease × (poço OU contrato)**. Uma lease gera N linhas: uma por unit agreement (K…), uma por poço (nº interno `#####-000` + API de 10 dígitos), uma por title opinion (T0…), uma por assignment/JOA. Um DPU aparece como `K1402139 | DECL OF POOLED UNIT- JOSH B UNIT | UNIT AGREEMENT`.

**O que ele prova** (e é muito): lease→unit, lease→poço (com API e WELL PROD STATUS), lease→title opinion, lease→assignment/JOA, mais EXP DATE / EXT EXP DATE / PROPERTY STATUS / RIGHTS HELD por lease.
**O que ele NÃO prova**: trato. Não há coluna de tract em nenhuma das abas — ver veredito P1.

### Ordenação — a parte cara
- **Sheet1: ordenada por LESSOR (A→Z)**, com os nomes iniciados por espaço vindo primeiro (` BILLE CHARLES WELLS`, ` DIANNA LYNN KIRKLAND`, ` SUZANNE SCHMIDT`…), depois `1ST SOUTHWEST`, `3LW LLC`, `7 STARS RANCH`, `77 OIL`, `A BENTON COCANOUGHER`… → **as leases de um mesmo unit ficam ESPALHADAS pelas 328 janelas.** Não varra.
- **Sheet2: ordenada por LEASE NO (ascendente)**, ~10 linhas por lease — mas a janela 1 começa em `0221714-020`, não no menor nº de lease do corpus. A cauda (janela 275) são **linhas órfãs sem lease**, só contrato (T0…/K…) com as 14 primeiras colunas vazias. **Não presuma que a lease alvo está em Sheet2**: leases abaixo de 0221714 podem não estar nessa aba (estão em Sheet1). Confirme antes de gastar janelas.

### CUSTO — leia isto antes de abrir
**~60–64 mil caracteres por janela** (≈15k tokens). 328+275 = 603 janelas ⇒ varrer é impossível. Consequências práticas:
- Para **um** unit, o retorno de garimpar o XREF lease a lease é baixo: a mesma lease já tem lessor/lessee/data no Exhibit "A" da DPU, e o vínculo unit→poço sai de graça da `well list` (1 janela, ordenada por WELL NAME).
- Use o XREF quando precisar de **EXP/EXT EXP DATE e PROPERTY STATUS por lease**, e só depois de localizar a janela.
- `search_corpus` não devolve nº de janela — não resolve a localização e ainda cospe a lista de arquivos não pesquisáveis.
- **Registre a janela** em que cada bloco de leases foi achado, na ficha da unidade: é a única forma de a próxima unidade não pagar a busca de novo.
