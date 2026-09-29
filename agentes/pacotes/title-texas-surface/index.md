---
type: Domain Pack
title: title-texas-surface
description: Surface title por tract no Texas (Cibola / BBT-SNN), cadeia desde janeiro de 1966 até a through date.
status: draft
generated:
  by: cowork/claude-opus-5-5
  at: 2026-09-27
verified: []
sources:
  - resource: docs/CIBOLA_RETROSPECTIVA_1128_2026-09-21.md
    id: retro1128
  - resource: docs/CIBOLA_PREPARACAO.md
    id: prep
---
# title-texas-surface

Pacote derivado da retrospectiva do BBT-SNN-1128 [^retro1128] e da preparação Cibola [^prep]. Fatos dominiais do 1128 e do 1129 ficam nos Case Files dessas units e não entram aqui.

## Fluxo padrão (gates que o Coordenador instancia)

| Gate | Tarefas | Funções |
|---|---|---|
| 0 Preflight | confirmar tract, PID, county, legal description, marco jan/1966, through date; árvore canônica vazia; template e exemplo canônico; registro de fontes, acessos, cobertura temporal e custo; fila externa (PACER, SOS, county/probate/court); ledgers de instrumentos e de buscas negativas; matriz de cobertura | Coordenador, operador |
| 1 Seed | tax card, tax map, captura integral dos deeds citados e lançamento imediato no runsheet; mapa de owner, predecessores, abstracts, subdivision/lot, prior references, variantes de nome | Pesquisador, Arquivista, Classificador, Examinador |
| 2 Cadeia e ônus | buscas em lote por abstract, subdivision/lot, partes (backward/forward), prior references; gravames voluntários e involuntários, releases, easements/ROW, restrictions, probate/divorce/corporate authority; gaps viram pedidos externos no mesmo dia | Pesquisador, Examinador |
| 3 Captura e reconciliação contínuas | por documento: captura integral, QA visual, nome canônico, hash, ledger, linha da planilha, efeito, pendência; reconciliar ledger × arquivos × planilha a cada lote | Arquivista, Redator |
| 4 Dupla revisão | verificação cega documento a documento e da continuidade da cadeia; divergência material vira questão explícita | Verificador, Árbitro |
| 5 QA e upload | estrutura × canônico, ordem cronológica, partes, datas, referências, legal descriptions, duplicatas, alocação territorial, fórmulas, merges, links, ausência de controles internos; `PARTIAL` enquanto houver dependência material | QA de pacote, operador |

## Fontes

| Fonte | Uso | Regra |
|---|---|---|
| CountyRecords (Terrell) | índice e preview | preview e captura integral, sem download; registrar saldo de views; série de deeds of trust começa em 06/11/1968 |
| TexasFile | localizar e indexar | cópia vem da fonte autorizada do projeto |
| County Clerk | gravames anteriores à cobertura do portal | pedido externo com custo aprovado |
| PACER, SOSDirect, GLO | aba Federal Court, situação de pessoas jurídicas, patentes | conta e custo aprovados pelo operador |
| Drive da PLM | pacote, planilha, links | documento sobe antes do link; planilha como nova versão do mesmo arquivo |

## Pendências para o pacote ficar utilizável

1. Template e exemplo canônico formalizados como mapa de campos (abas Cover Sheet, Surface, Mortgages, Oil/gas, etc.).
2. Vocabulário fechado de categorias e motivos de exclusão para surface.
3. Esquemas de saída específicos (linha de runsheet de surface, exceção da capa).
4. Itens da bateria de avaliação a partir do 1128 e do 1129 (gabaritos em quarentena).

[^retro1128]: `docs/CIBOLA_RETROSPECTIVA_1128_2026-09-21.md`, §§2 e 4.
[^prep]: `docs/CIBOLA_PREPARACAO.md`.
