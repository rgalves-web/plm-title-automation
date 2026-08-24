# CONSERTO DEFINITIVO — CHECKPOINT 3 (encerramento da ordem + Etapa F)
**Data:** 2026-08-24 · **Branch:** `conserto-definitivo` · **Executor:** Code
**Ordens:** `CODE_INSTRUCTIONS_CONSERTO_DEFINITIVO.md` (Etapa E) + `CODE_INSTRUCTIONS_ETAPA_F_CUSTO.md`
**Decisões do operador registradas:** medição parcial do replay 1 ACEITA como CP3-medição;
replay 1 preservado como artefato (não terminar); NENHUMA exceção de teto; replay 2 com
orçamento fresco de US$ 25.

---

## 1. O veredito em uma frase

O fluxo consertado da Etapa F multiplicou a produtividade por dólar (memória: 11→318 campos
provados pelo mesmo dinheiro; TOs achados e lidos; delta no prompt; cache ~90-97%), o teto de
US$ 25 funcionou como mecanismo (parou o ship no orçamento, sem estourar em silêncio) — e a
prova de 90% de cobertura da Josh B **não coube em $25**: o replay 2 fechou em **31,7%** com a
projeção cortada pelo teto. O número pedido pelo doc governante está colhido e explicado (§6).

## 2. Replay 1 × Replay 2 — a comparação honesta

| Métrica | Replay 1 (fluxo E) | Replay 2 (fluxo F) |
|---|---|---|
| Corpus | 200 arquivos (1.132 docs), TOs presentes mas NÃO alcançados | 198 únicos por md5 (1.131 docs), **TOs/DPU/assignments achados e lidos** |
| Abertura | 11 campos por $4.60 | **292 campos por $11.02** (inclui Triador $0.93/1.130 rótulos) |
| Prompt do `continuar` | ~1.100 nomes reapresentados por ciclo | **delta real** (4 nomes) + inventário agregado |
| Memória ao fim | 67 escritos + 11 brancos ($14.50) | **318 escritos + 89 brancos** ($14.88) |
| Custo por campo provado na memória | ~$0.22 | **~$0.047** (4,6× melhor) |
| Ship | projeção 33 células; auditoria r1 33/16 reprovadas; correção morreu sem créditos | projeção **87 células + 28 brancos** e parada LIMPA no teto; auditoria não coube |
| Cobertura do gabarito (2.905 células) | 26,7% (33 escr. + 742 brancos) | **31,7%** (182 escr. + 739 brancos) |
| Das escritas alinhadas | 13 concordam · 9 equiv. · 11 divergem | **51 concordam · 15 equiv. · 15 divergem** |
| Custo total | $19.83 (+ ~$1.6 não persistidos, declarado) | **$25.2132** (tudo persistido, por turno) |

## 3. Custo por comando e caches (replay 2)

| Comando | Custo | Hit-rate do prompt cache (cache_lido/entrada_total) |
|---|---|---|
| triador (Haiku, 59 turnos, 1.130 rótulos) | $0.9294 | 97% |
| unidade (Examinador Opus, 39 turnos) | $10.0893 | 96% |
| continuar (delta: 4 docs + P1) | $3.8636 | 89% |
| ship 1ª (projeção 20 turnos, caiu sem créditos) | $6.9569 | (log por turno) |
| ship 2ª (projeção 22 turnos, **parada pelo teto**) | $3.3740 | (log por turno) |
| **Total** | **$25.2132** | — |

- Tokens Triador × Examinador (abertura): Haiku 4,32M entrada-total/75k saída ($0.93) fez o mapa
  que poupou o Opus (7,95M/187k, $10.09) de varrer o corpus às cegas.
- **Cache global de páginas** (`data/_page_cache`): 100% de hits nas leituras repetidas
  (71/71 consultas nos fechos) — as páginas pagas pelo replay 1/rodadas antigas serviram o 2.
- O estouro residual de $0.2132 sobre o teto é granularidade de turno (o laço só vê o custo
  após o turno que cruzou a linha) — declarado, não silencioso.
- A suspeita de `cache_leitura` baixo (F2) não se confirmou no fluxo novo: 89–97%.

## 4. Aceites do CP3 — item a item, sem maquiagem

| Critério | Resultado |
|---|---|
| ≥90% das células do DDR à mão cobertas | **NÃO — 31,7%.** O teto cortou a projeção (87 de ~400 ações); a memória tinha 318 campos provados que não chegaram ao DDR. |
| 0 célula reprovada embarcada | **NÃO AVALIADO no replay 2** (auditoria não coube no teto) — e **nada foi embarcado/publicado**: kit não montado, `SUBMISSION PLM` inexistente. Mecanismo provado na sintética (CP1: 59/59, 8 corrigidas). |
| Auditoria 100% `gpt-5.6-terra` sem carimbo | Não rodou no replay 2 (teto). Provada na sintética (6 células reais, sem carimbo, custo na tabela). |
| Custo ≤ US$ 25, parar ao bater | **O MECANISMO CUMPRIU**: recusa limpa no teto, parada da projeção, tudo contabilizado (+$0.21 de granularidade declarado). |
| Hash de fórmulas idêntico | **SIM** — validado em todo save da projeção (write_workbook aborta na divergência; DDR.xlsx do replay 2 passou). |
| Kit completo | **NÃO** (teto). Mecanismo provado na sintética (9/9 md5, publicar congelado). |
| Quarentena provada no log | **SIM** — proteção ativa em todos os comandos; sondas registradas em unidade/continuar (2 bloqueios cada, 0 tentativas do run). Nos ships que caíram por exceção o registro da sonda não persistiu (o driver grava ao fim) — lacuna de registro anotada, não de proteção. |
| Conflito 62 vs 67 resolvido pela auditoria | **PARCIAL**: o denominador 67 foi PROVADO por contagem citada página a página (43 na p.3 + 24 na p.4 do Exhibit "A", K1402139). A fonte divergente "62" não emergiu até o corte e a auditoria não rodou — sem confronto. |
| Amostra ≥5 reprovações da rodada 1 explicadas | **NÃO HÁ RODADA 1 no replay 2.** Material existente: a divergência Sonnet×OpenAI `Curative!A3` da sintética (ordinal julgado como fato → ficha + prompt calibrados) e as 16 reprovadas do replay 1 (vereditos perdidos antes do conserto de persistência — hoje fluiriam ao disco). |

## 5. O que os replays compraram além dos números (robustez, tudo testado)

Seis defeitos reais achados por rodadas reais e consertados na branch: resposta cortada em
`max_tokens` tratada como fim (embarcou DDR vazio) → instrução de refazer com teto de cortes;
timeout/conexão e 429/5xx/529 → retry com backoff; ledger/vereditos/logs de sessão fluem ao
disco POR TURNO (3 perdas de contabilidade/trabalho no dia); `auditar_tudo` estourava com
write_cell em faixa → faixa filtrada (não colocada por regra); path relativo no kit;
UnicodeEncodeError engolindo o registro de custo. Suíte: **926 verdes**.

## 6. O número para a decisão (meta do doc governante: "medir e revisitar com número na mão")

Com o fluxo F, a memória custou ~$0.047/campo provado e a projeção ~$0.078/ação
($6.96+$3.37 ÷ ~133 ações efetivas + overhead do mapa 17k). Extrapolação honesta para
convergir a Josh B (2.905 células do gabarito; faltam ~2.400 células entre escrita e branco):
**~$35–50/unit** no estado atual — 40–100% acima do teto. As três alavancas seguintes, por
impacto (nenhuma implementada — ficam para ordem nova, linhas no BACKLOG):
1. `write_cells`/`record_blanks` em LOTE na projeção (a projeção ainda é 1 célula/chamada —
   o mesmo conserto F3 da memória, não aplicado ao ship);
2. projeção com memória em DELTA (o dump completo de 318 campos + mapa do template a cada
   sessão de ship custa ~metade da projeção);
3. retomada de ship do ledger salvo (hoje re-projeta do zero após queda — o ledger por turno
   já existe, falta o `ship --continuar`).

## 7. Artefatos

Replay 1 (`data/units/_josh_b_replay/`) e replay 2 (`_josh_b_replay2/`) preservados intactos:
estados, memórias, ledgers, logs por turno, PEDIDOS/PERGUNTAS respondidas só com registrado,
`MEDICAO_E3.json` de ambos, `POPULACOES.md` declaradas antes, `_quarentena_prova.json`.
Horas de operador: 0.3h (replay 1) + 0.1h (replay 2, entrega de planilhas + P1). Nada nas
units entregues; `WORKBENCH_STATUS.md` atualizado (baseline nova; pré-conserto rebaixado a
histórico).

---

**Fim da ordem CONSERTO_DEFINITIVO + Etapa F. Aguardando o aceite final do operador — a
verificação pelos bytes é da sessão Cowork. Decisões abertas para a próxima ordem: as três
alavancas do §6 e se a Josh B converge numa Etapa G (com o mesmo teto, fluxo mais barato) ou
se o teto por unit é revisado com este número na mão.**
