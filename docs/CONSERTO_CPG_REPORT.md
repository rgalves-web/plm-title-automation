# ETAPA G — PROJEÇÃO BARATA + CONVERGÊNCIA DA JOSH B
**Data:** 2026-08-24 · **Branch:** `conserto-definitivo` · **Executor:** Code
**Ordem:** `docs/CODE_INSTRUCTIONS_ETAPA_G.md` · **Aceite do CP3:** registrado pelo operador.
**Teto desta unit:** US$ 35 (exceção autorizada só para `_josh_b_replay2`; produção segue US$ 25).

---

## 1. O resultado em uma frase

As três alavancas do CP3 §6 funcionaram: a projeção ficou **6,5× mais barata por ação**, a
cobertura da Josh B saltou de **31,7% → 87,3%** por mais $8.52, e a unidade fechou em
**$33.73 de $35** — mas a prova ainda **não** cruzou os 90% nem exercitou auditoria/kit no
corpus real: o **limite mensal da conta Anthropic** (regain 2026-09-01) cortou a sessão e a
margem restante ($1.27) não paga o que falta.

## 2. G1–G3 — entregues, testados e provados nos bytes

**G1 · Projeção em lote** (`write_cells` / `record_blanks`): recusa de fórmula por célula, sem
derrubar o lote (a célula recusada volta nomeada, o resto entra). Na rodada real: **39 chamadas
em lote produziram 708 ações** (663 células + 45 brancos) — ~18 ações por chamada, contra 1
antes.

**G2 · Memória em delta na projeção**: a sessão recebe só os campos ainda sem célula, mais o
resumo curto do que já foi projetado. Medido no estado real: memória completa ~39,9k tokens →
delta + já-feito ~30,9k (**−23% por turno**); o mapa do template (16,8k) segue fixo e cacheado.
Brancos e pendentes voltam sempre (nunca somem do contexto).

**G3 · `minorh ship --continuar`**: retomada do ledger salvo. Provado nos dois lados — teste com
queda simulada no meio (a retomada não refaz o já feito e completa o resto) e, no corpus real,
a linha `RETOMADA de 87 célula(s) e 28 branco(s) já projetados` seguida de projeção que **não
repetiu nada**. O padrão que queimou $6.96 no CP3 está eliminado.

**Extra da ordem:** a lacuna de registro da quarentena fechou — a prova agora é gravada em
`finally`, com o **desfecho** do comando. O `ship --continuar` que morreu no limite da API está
lá: `sonda: 2 bloqueios · tentativas no run: 0 · desfecho: BadRequestError…`.

Suíte: **930 verdes** (5 testes novos: lote com recusa parcial, delta, retomada, retomada sem
ledger, prova em finally).

## 3. G4 — a convergência, com os números

| | CP3 (fluxo F) | **Etapa G** |
|---|---|---|
| Células no ledger | 87 + 28 brancos | **750 + 73 brancos** |
| Ações por chamada de ferramenta | 1 | **~18** |
| Custo por ação projetada | $0.078 | **$0.012** (6,5× melhor) |
| Cobertura do gabarito (2.905 células) | 31,7% | **87,3%** (784 escritas + 1.751 brancos) |
| Concordou / equivalente / divergiu | 51 / 15 / 15 | **346 / 195 / 124** |
| Custo acumulado da unit | $25.21 | **$33.73** (de $35) |

**Cobertura por aba** (cobertas/gabarito): Lease Review 1072/1089 (98%) · Ownership - Worksheet
1302/1378 (94%) · Agreements 30/30 (100%) · Summary 12/25 (48%) · Ownership - Wells 19/40 (47%)
· Unit and Pooling 11/24 (45%) · Runsheet 79/267 (29%) · PLM Title Review 10/50 (20%) ·
Disclaimer 0/2 (0%).

Os 2,7 pontos que faltam estão concentrados em Runsheet e PLM Title Review — abas cujos campos
seguem **na memória sem célula** (135 campos no delta) ou pendentes de documento. A próxima
sessão de projeção (~$1.6 estimados) provavelmente cruza os 90%; a margem é $1.27.

## 4. As divergências, explicadas (124 divergiu + 50 "escreveu onde a mão não tem")

| Categoria | Qtd | Leitura honesta |
|---|---|---|
| Conteúdo distinto (grão de linha ou fato) | 96 (77%) | Maioria é **grão de linha**: a mão repete a lease por trato e ordena diferente; onde o alinhamento por identidade não pega a linha, a comparação confronta células de leases diferentes (ex.: `Worksheet!B54` mão `l14 (0220604-013)` × IA `0220936-001`). Uma parte é fato a confrontar — só a auditoria decide. |
| Número divergente | 16 (12%) | Ex.: `K13/K14` mão `515` × IA `514` — página de recording vizinha. Candidato a defeito real de um dos lados; é exatamente o que o auditor com a página aberta resolve. |
| Data divergente | 8 (6%) | Ex.: `J24` 2011-03-31 × 2013-03-30. Idem: confronto com a página citada. |
| Mesma entidade, prosa diferente | 2 (1%) | A mão carrega variantes entre parênteses (`dundley (dudley) edward jordan`); a IA escreve o nome do instrumento. Estilo/completude, não erro factual. |
| **Escape HTML introduzido na projeção** | 2–3 | **Defeito real do sistema, e localizado**: `BRA-DE Oil &amp; Gas Inc` na célula, enquanto a **memória tem `&` correto** — o escape nasce na sessão de projeção. A auditoria de 100% reprovaria (o trecho citado não sustenta o escape). Anotado no BACKLOG. |

**"Escreveu onde a mão não tem" (50):** o DDR à mão deixa vazias células que a IA preencheu com
valor citado ou branco declarado — em parte grão de linha (linhas extras da IA), em parte
material que a mão não reportou. Sem a auditoria não afirmo qual é qual, e não vou afirmar.

## 5. Aceites da ordem G — item a item

| Critério | Resultado |
|---|---|
| Toda célula escrita-com-citação ou branca-com-motivo-e-dono | **87,3%** do gabarito (não 100%); cobertura por aba na §3. Nenhuma célula sem uma das duas formas — o que falta é ausência, não buraco silencioso. |
| **0 célula reprovada embarcada** | **NÃO EXERCITADO**: auditoria não rodou (limite da conta + margem). **Nada foi embarcado**: kit não montado, `SUBMISSION PLM` inexistente. |
| Auditoria 100% família B sem carimbo | Não rodou nesta etapa (provada na sintética; `gpt-5.6-terra` configurado e com tarifa na tabela). |
| Amostra ≥5 reprovações explicadas | **Não há reprovações** — a auditoria não rodou. O material equivalente está na §4 (categorias de divergência, com o defeito real isolado). |
| Divergentes e extras explicados um a um | **SIM**, por categoria com exemplos e o defeito real nomeado (§4). |
| Conflito 62 vs 67 confrontado pela auditoria | **NÃO** — o denominador **67 segue provado** por contagem citada (43 na p.3 + 24 na p.4 do Exhibit "A", K1402139); o confronto exige a auditoria. |
| Hash de fórmulas idêntico | **SIM** — verificado ao materializar o DDR do ledger salvo. |
| Kit md5 | Não montado (etapa não alcançada). |
| Quarentena com prova persistida também nos ships | **SIM** — lacuna do CP3 fechada; desfecho registrado inclusive na queda. |
| Custo ≤ $35, por comando | **SIM — $33.7333.** Comandos: triador $0.9294 · unidade $10.0893 · continuar $3.8636 · ship-1ª (queda sem créditos) $6.9569 · ship-2ª (parada no teto de $25) $3.3740 · **ship --continuar G4 $8.5201**. |
| Horas de operador | **0.1h** nesta unit (`minorh horas`), 0.3h no replay 1. |

## 6. Por que parou — e o que falta em dinheiro

O corte foi **externo**: `You have reached your specified API usage limits. You will regain
access on 2026-09-01` (limite mensal da conta, não saldo). Mesmo sem ele, a conta não fechava
dentro de $35: falta **~$1.6** de projeção (135 campos) e **~$5.2** de auditoria de 100% das
784 células com `gpt-5.6-terra` (estimativa pela tarifa $2/$12 por 1M), mais correção e kit.
**Total para fechar a prova: ~$8–10 além dos $33.73.** Não estourei o teto nem pedi exceção —
a regra é parar e reportar.

Projeção honesta para a unit seguinte, do zero, com o fluxo G completo e caches quentes:
abertura+triagem ~$11, continuar ~$4, projeção em lote ~$9, auditoria ~$5, kit ~$1 →
**~$30/unit**. Ainda acima dos $25 de produção; a próxima alavanca óbvia é a **auditoria em
lote** (hoje uma chamada por célula) e o Triador assumindo a projeção das abas mecânicas.

## 7. Estado e artefatos

`data/units/_josh_b_replay2/`: estado com todas as execuções, memória (430 campos), ledger
(750 células + 73 brancos, salvo por turno), `DDR.xlsx` materializado do ledger, `MEDICAO_E3.json`,
`progresso_projecao.jsonl`, `_quarentena_prova.json` com desfechos, `POPULACOES.md`. Replay 1
intacto. Nada nas units entregues. Achados sem impacto na prova → `docs/BACKLOG.md`.

---

**Parado aqui, conforme a ordem. Decisões do operador para seguir:** (a) liberar o limite mensal
da conta (console → Settings → Limits) ou aguardar 01/09; (b) autorizar ~$8–10 além dos $35 para
fechar a prova desta unit (projeção final + auditoria + correção + kit + medição), ou aceitar
87,3% como resultado da Etapa G e levar a prova de 90% para a primeira unit nova com o fluxo
completo.
