---
type: Domain Pack
title: title-texas-oil-gas-dd
description: Due diligence de unidades de óleo e gás no Texas com entregável DDR (Project Emirates, BKV122TX).
status: draft
generated:
  by: cowork/claude-opus-5-5
  at: 2026-09-27
verified: []
sources:
  - resource: knowledge_okf/index.md
    id: okf
  - resource: CLAUDE.md
    id: claude
  - resource: docs/HANDOVER_CASEFILE_2026-09-03.md
    id: handover
---
# title-texas-oil-gas-dd

O conhecimento deste pacote já existe em `knowledge_okf/` [^okf] (entidades, chaves de identidade, categorias e destinos no DDR, motivos de exclusão, capítulos do Manual Técnico, precedentes) e nas regras do operador registradas no handover do Case File [^handover]. Este índice organiza esse acervo por função; a migração física das fichas é tarefa da etapa A.

## Fluxo padrão

| Gate | Tarefas | Funções |
|---|---|---|
| 0 Abertura | censo do acervo; cruzamento DPU Exhibit A × XREF (duas abas) × Lease & Mineral Schedule, ciente de dupla gravação Cooke/Montague; pull list de cartório no dia 1 | Coordenador, Classificador, Pesquisador |
| 1 Perímetro | população de leases do Exhibit A (denominador fixo); TOs e supplements pela cert date; tracts | Examinador, Verificador |
| 2 Coleta | leases, memorandos, DPU, TOs, well files; buscas negativas (DOTO/DOI) com população declarada | Pesquisador, Arquivista |
| 3 Exame | lease review, runsheet suplementar (só de registro, após cert date), curative, ownership, WI/NRI só com evidência | Examinador, Verificador, Árbitro |
| 4 Projeção | DDR célula a célula com proveniência; fórmulas protegidas | Redator |
| 5 Pacote | kit Phase I carbon-copy, Missing Files, checklist, auditoria 100% | QA de pacote, operador |

## Mapa do acervo existente por função

| Função | Fichas em `knowledge_okf/` |
|---|---|
| Classificador | `categories-*`, `category-to-ddr-*`, `entities-*`, `identity-keys-*`, `transmittal-cover-is-not-the-document-fixture` |
| Pesquisador | `cartorio-*`, `coleta-courthousedirect-receita-provada`, `pull-list-de-cartorio-derivada-do-exhibit-a-vs-pastas-de-files`, `sources-*`, `protocolo-captura-viewer-cartorio` |
| Examinador | `manual-7*`, `manual-8*`, `manual-9*`, `precedente-*`, `exhibit-a-da-dpu-vs-recital-recorded-do-lease`, `formulario-eog-*` |
| Redator | `ddr-template-structure-*`, `manual-11*`, `manual-12*`, `runsheet-style`, `veredito-grao-da-aba-ownership-worksheet-uma-linha-por-lease` |
| QA de pacote | `manual-15-catalogo-de-validacoes`, `sop-10-formato-e-empacotamento`, `padrao-montagem-pacote-phase-i`, `missing-files-rotulos-canonicos` |
| Todas | `exclusion-reasons-*`, `engagement`, `bpm-plm-due-diligence-leasehold-escopo` |

Fichas específicas de uma unit (`unidade-josh-b-unit-montague`, `cadeia-bra-de-*`, `bra-de-top-leases-*`) são fato de caso e devem migrar para o Case File da unit, fora do pacote.

## Bateria de avaliação

Josh B, Bowen A, Webb B, Maxwell A, com gabaritos em quarentena por identidade.

[^okf]: `knowledge_okf/index.md`.
[^handover]: `docs/HANDOVER_CASEFILE_2026-09-03.md`, §5.
