# CONSERTO DEFINITIVO — CHECKPOINT 2
**Data:** 2026-08-24 · **Branch:** `conserto-definitivo` · **Executor:** Code
**Aceite do CP1:** registrado pelo operador em 24/08 (verificação Cowork pelos bytes).
**Parado aqui, aguardando aceite do operador antes da ETAPA E (replay da Josh B).**

## 1. Pendências do CP1, fechadas primeiro

- **Auditor OpenAI (C3) exercitado de verdade.** Com a chave ativada no `.env` pelo operador,
  `Auditor.escolher()` escolheu `openai/gpt-4o-mini` **sem carimbo de limitação**. Chamadas
  reais reauditaram uma amostra de 6 células do DDR embarcado da sintética: 5 aprovadas,
  **1 reprovada — `Curative!A3`** ("a página cita cinco leases, mas o valor escrito é
  inconsistente"), célula que o Sonnet havia aprovado. É exatamente o desacordo entre famílias
  que a regra existe para pegar; o kit publicado está congelado, então fica **registrado para o
  operador** decidir se reabre (artefato: `_minorh/ship/AUDITORIA_OPENAI.json`; execução
  registrada no estado; tokens: 9.363 entrada / 299 saída; custo fora da tabela RATES —
  reportado em tokens).
- **P1 respondida e processada como precedente.** Observação honesta: a resposta **não estava**
  no `PERGUNTAS.md` quando verifiquei; escrevi com as palavras exatas ditadas pelo operador na
  conversa ("Nenhuma das duas fontes prevalece por si… branco declarado + pedido de verificação
  no cartório", base Webb B). `minorh continuar` processou ($0.4283): ficha global
  `precedente-divergencia-de-referencia-de-registro-resolve-se-no-cartorio` (tipo `veredito`,
  visível ao `get_precedent`), regra `exhibit-a-da-dpu-vs-recital-recorded-do-lease` atualizada,
  e o REGISTRO da −003 rebaixado a **branco declarado** conforme o veredito (brancos 1→2).
- **Retry de erro transitório no laço.** Dois 529 (API sobrecarregada) seguidos mataram o
  `continuar` no turno 1 e bloquearam a ordem do operador — virou conserto:
  `_create_com_retry` em `loop.py` (5 tentativas, backoff exponencial, só 429/5xx/529; erro
  definitivo não repete). Testado; o BACKLOG registra a promoção. Na prática, o retry segurou
  3 ondas de 529 na rodada seguinte.

## 2. ETAPA D — o que foi entregue

- **D1 — prompt do dia-1 em `cmd_unidade`** (instrução + fichas, zero módulo): censo primeiro;
  **escopo cruzado** Exhibit "A" × as DUAS abas do XREF × Lease & Mineral Schedule,
  county-aware (ficha `lease-mineral-schedule-recording-multi-condado`), toda divergência vira
  pergunta ou pedido; **pull list de cartório desde o dia 1** — instrumento sem arquivo mas com
  Book/Page (ou reception+ano) determinístico vira item de PEDIDOS.md com referência exata,
  condado e caminho provável do viewer (ficha `cartorio-courthousedirect-arvore-e-busca`);
  itens do mesmo lugar compartilham o `onde` literal.
- **D2 — PEDIDOS.md empacotado por sentada**: `escrever_pedidos` agrupa os itens abertos por
  `onde` (`## Sentada: <onde> — N item(ns)`). Agrupar por string igual é plumbing; o `onde` de
  cada item é decisão do modelo. Invariante "one brief item per decision" mantido.
- **D3 — `minorh painel`**: leitura pura, zero modelo, zero escrita; varre a pasta-mãe por
  `<unidade>/_minorh/estado.json` e imprime uma linha por unidade com censo · escritos ·
  brancos · pendentes · pedidos · perguntas · $ · horas · último comando/data.

## 3. A prova (critério do CHECKPOINT 2)

**Abertura fresca da sintética** (`data/units/_cp2_sintetica`, leases −004 e −005 removidas do
corpus — ambas com Book/Page determinístico no Exhibit "A"). `minorh unidade` real: censo 59,
55 escritos, custo **$1.4428**. O `PEDIDOS.md` da abertura saiu com:

- **Pull list determinística**: PED-001 (−004, Vol. 100, Pg. 4) e PED-002 (−005, Vol. 100,
  Pg. 5) com caminho do viewer (`Deeds_OPR_ByVolume/<range>/100/100_<pág-inicial>.tif`,
  listagem gratuita antes de pagar, início ≤ pág. citada, fallback ByYearDocId/2011) — a ficha
  A3 aplicada; PED-003 pede a certidão da −003 **pelas duas referências divergentes** (Pg. 3 E
  Pg. 33), coerente com o precedente P1; PED-004 (probate) declara que NÃO há book/page
  determinístico e por quê.
- **Agrupamento por sentada**: 2 sentadas — "cartório de Palo Duro — CourthouseDirect" (4
  itens, resolvidos numa listagem só do Vol. 100) e "data room do seller" (2 itens: XREF com
  as duas abas e a Schedule com RECORDING íntegro — o escopo cruzado do D1 pedindo as fontes
  que faltam, em vez de fingir que o cruzamento foi feito).

**`minorh painel "data/units"`** mostra as **2 unidades**, uma linha cada
(`_saida_painel.txt`):
`_cp1_sintetica: censo 60 · escritos 64 · brancos 2 · pendentes 7 · pedidos 3 · perguntas 0 · $5.5596 · 0.2h · último: continuar 2026-08-24`
`_cp2_sintetica: censo 59 · escritos 55 · brancos 1 · pendentes 14 · pedidos 6 · perguntas 1 · $1.4428 · 0h · último: unidade 2026-08-24`

## 4. Suíte e custos

- Suíte: **918 passed** (3 testes novos: retry transitório, sentadas do PEDIDOS, painel).
- Custos reais desta etapa: $0.4283 (continuar P1) + $1.4428 (abertura CP2) + auditor OpenAI
  em tokens (9.363/299; fora da tabela de preços do repo). Acumulados: `_cp1_sintetica`
  $5.5596 · `_cp2_sintetica` $1.4428 — tetos de $25/unit intactos.

## 5. Aberto / para o aceite

- A divergência **Sonnet × OpenAI em `Curative!A3`** do kit já publicado (congelado): o
  operador decide se reabre a entrega sintética ou aceita como achado de calibração. Nenhuma
  ação tomada — pacote entregue é intocável.
- `gpt-4o-mini` é o default histórico do ramo B (`MINORH_AUDITOR_OPENAI` troca sem código);
  se o operador preferir um modelo OpenAI mais novo, é uma variável de ambiente.
- A pergunta P1 da `_cp2_sintetica` (a mesma divergência da −003, reaberta pela abertura
  fresca) responde-se sozinha na próxima `continuar` via `get_precedent` — ou fica aberta até
  a certidão, conforme o precedente agora manda.

---

**Aguardando aceite registrado do operador para seguir à ETAPA E — replay da Josh B
(corpus in-place, quarentena com prova no log, populações declaradas antes de rodar,
`compare.py` contra o DDR à mão, aceite ≥90% / 0 reprovada embarcada / ≤ US$ 25).**
