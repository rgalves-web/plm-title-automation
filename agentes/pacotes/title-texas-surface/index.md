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

## Protocolo obrigatório — 01/10/2026

Atualização vigente: protocolo **1.2**, comunicados fornecidos pelo usuário. Q2 exige pesquisa grantor/grantee de toda parte da cadeia: nomes/variantes/capacidades, períodos, fontes, resultados completos e reconciliação. Remissões não substituem buscas nominais; busca conjunta só cobre ambos os índices quando comprovada. Examinar leases e atos minerais encontrados no escopo surface, sem iniciar automaticamente mineral title. Padrão definido pelo Lead/PM por tipo (Derek no contexto Cibola), incluindo alinhamento, wrapping, estilos, sombreamento e bordas. Spell Check inclui todas as notas/comentários; consulta aos SMEs designados deve ser preparada cedo. Link/manual PREP encontrados e acesso observado não equivalem a execução. Consultar publicação ativa e evidências no README da governança.

Antes de executar qualquer gate Cibola, ler `../Land Cibola Surface Titles/00_Governanca/PROTOCOLO_SUBMISSAO_PLM.md` (caminho relativo à raiz do repositório). Fonte: mensagem atribuída a Marc Reyes fornecida por Renato e adotada explicitamente nesta data. O protocolo central contém os critérios Q1–Q6, evidências exigidas e formulário interno; não manter outra versão normativa neste pacote.

Toda submissão, parcial ou final: padrão exato das entradas de Derek, PREP real da versão submetida, Spell Check, conferência documental independente e resolução das questões técnicas com SME quando necessário. Ficha de treinamento não comprova execução. Uploads de trabalho em andamento estão autorizados como WORKING DRAFT, com versão e pendências explícitas. Project Log permanece somente leitura. A marca PARTIAL em controles históricos deve ser apresentada ao usuário como WORKING DRAFT enquanto houver lacuna material.

## Fluxo padrão (gates que o Coordenador instancia)

| Gate | Tarefas | Funções |
|---|---|---|
| 0 Preflight | confirmar tract, PID, county, legal description, marco jan/1966, through date; árvore canônica vazia; template e exemplo canônico; registro de fontes, acessos, cobertura temporal e custo; fila externa (PACER, SOS, county/probate/court); ledgers de instrumentos e de buscas negativas; matriz de cobertura | Coordenador, operador |
| 1 Seed | tax card, tax map, captura integral dos deeds citados e lançamento imediato no runsheet; mapa de owner, predecessores, abstracts, subdivision/lot, prior references, variantes de nome | Pesquisador, Arquivista, Classificador, Examinador |
| 2 Cadeia e ônus | buscas em lote por abstract, subdivision/lot, partes (backward/forward), prior references; gravames voluntários e involuntários, releases, easements/ROW, restrictions, probate/divorce/corporate authority; gaps viram pedidos externos no mesmo dia | Pesquisador, Examinador |
| 3 Captura e reconciliação contínuas | por documento: captura integral, QA visual, nome canônico, hash, ledger, linha da planilha, efeito, pendência; reconciliar ledger × arquivos × planilha a cada lote | Arquivista, Redator |
| 4 Dupla revisão | verificação cega documento a documento e da continuidade da cadeia; divergência material vira questão explícita | Verificador, Árbitro |
| 5 QA e submissão | aplicar Q1–Q6 do protocolo central: Derek por tipo e linha; integridade documental e revisão independente; PREP real e evidenciado; Spell Check final; SME conforme questões; identidade da versão, fórmulas, impressão integral, links e ausência de controles internos. WORKING DRAFT com lacuna material. Toda submissão parcial/final exige conformidade | QA de pacote, operador |

## Fontes

| Fonte | Uso | Regra |
|---|---|---|
| CountyRecords (Terrell) | índice e preview | preview e captura integral, sem download; registrar saldo de views; série de deeds of trust começa em 06/11/1968 |
| TexasFile | localizar e indexar | cópia vem da fonte autorizada do projeto |
| County Clerk | gravames anteriores à cobertura do portal | pedido externo com custo aprovado |
| PACER, SOSDirect, GLO | aba Federal Court, situação de pessoas jurídicas, patentes | conta e custo aprovados pelo operador |
| Drive da PLM | consulta e uploads de trabalho em andamento autorizados por Renato | validar localmente; identificar versão/WORKING DRAFT e pendências; preservar entregas anteriores; verificar documento no destino antes de ligar; toda submissão parcial/final cumpre Q1–Q6; Project Log somente leitura |

## Pendências para o pacote ficar utilizável

1. Template e exemplo canônico formalizados como mapa de campos (abas Cover Sheet, Surface, Mortgages, Oil/gas, etc.).
2. Vocabulário fechado de categorias e motivos de exclusão para surface.
3. Esquemas de saída específicos (linha de runsheet de surface, exceção da capa).
4. Itens da bateria de avaliação a partir do 1128 e do 1129 (gabaritos em quarentena).

[^retro1128]: `docs/CIBOLA_RETROSPECTIVA_1128_2026-09-21.md`, §§2 e 4.
[^prep]: `docs/CIBOLA_PREPARACAO.md`.
