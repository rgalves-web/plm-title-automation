---
concept: veredito-grao-da-aba-ownership-worksheet-uma-linha-por-lease
type: veredito
sources:
- PERGUNTAS.md [P1] respondida pelo operador em 24/08/2026 (unidade _josh_b_replay2
  / Josh B Unit)
- 'regra do cliente: manual-9-1-ownership-report (Manual Tecnico v1.0 cap. 9.1; docs/SOP_DDR_PROJECT_EMIRATES.md
  §4)'
- lease to well and contract xref 06-16-2026 (1).xlsx p.0, 1:1, 2:1 (cabecalho das
  duas abas)
links:
- manual-9-1-ownership-report
- layout-workbooks-bkv122tx-well-list-project-log-e-xref
- ddr-template-structure-ownership-worksheet
- escopo-cruzado-quando-xref-e-schedule-nao-estao-no-corpus
unit: ''
confidence: alta — resposta do operador, vale como precedente nas 300 unidades
---

## VEREDITO — grão de linha da aba `Ownership - Worksheet`

**Pergunta (P1, Josh B Unit):** com 67 leases no Exhibit "A" da DPU e 4 tratos no Exhibit "C", e sem DOTO/DOI, o grão é (a) 1 linha por lease, (b) 1 linha por lease × unit tract, ou (c) 1 linha por trato com leases agregadas?

**RESPOSTA DO OPERADOR: (a) — UMA LINHA POR LEASE IN_SCOPE_REPRESENTED.** Não é decisão da unidade: é a regra registrada do cliente (`manual-9-1-ownership-report`, cap. 9.1 / SOP §4).

### Como aplicar
1. **Denominador da aba = nº de leases IN_SCOPE_REPRESENTED do Exhibit "A"**, não nº de tratos, não o produto lease×trato. O censo da aba é `nº de leases × colunas do cabeçalho`.
2. **Unit tract e TO tract são COLUNAS da linha da lease**, preenchidas *quando a amarração existir* — não são o grão da linha e nunca multiplicam linhas.
3. **Fonte da amarração lease×trato, nesta ordem:** Lease-to-Well XREF → DOTO/DOI. 
4. **Onde nada amarrar: BRANCO DECLARADO, dono = DOTO/DOI (pedido aberto). NUNCA inferido** — nem por proximidade de survey, nem por rateio de acreagem, nem por ordem do Exhibit "A".
5. Se a numeração do unit tract divergir da do TO tract, os dois vão em campos separados (cap. 9.1).

### Armadilha confirmada no campo (não repita o diagnóstico)
O **Lease-to-Well XREF do projeto BKV122TX NÃO amarra lease→trato**. As duas abas partilham o mesmo cabeçalho de 26 colunas e nenhuma é de trato:
`INCLUDE FLAG | LEASE NO | LESSOR | LESSEE | ACTIVE FLAG | RECORD TYPE | RIGHTS HELD | PROPERTY STATUS | LEASE DATE | EFF DATE | EXP DATE | EXT EXP DATE | STATE | COUNTY | WELL OR CONTRACT NB | WELL OR CONTRACT NAME | ACTIVE FLAG | RECORD TYPE | RIGHTS HELD | WELL PROD STATUS | AGMT DATE | EFF DATE | WELL OPERATOR | WELL API | STATE | COUNTY`
Ele amarra **lease→unit (K…)** e **lease→poço (nº interno + API)** — que é ouro para escopo e para a aba Wells — mas o trato **só sai da DOTO/DOI**. Logo, em unidade sem DOTO, a coluna de trato nasce branca para 100% das leases, e isso é resultado correto, não trabalho faltando.
