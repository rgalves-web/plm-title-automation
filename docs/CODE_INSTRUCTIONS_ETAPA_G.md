# ORDEM — ETAPA G: PROJEÇÃO BARATA + CONVERGÊNCIA DA JOSH B (fecha a prova)
**Data:** 2026-08-24 · **Autor:** sessão Cowork · **Aprovada pelo operador.**
Continuação na mesma branch, mesmas regras (LLM-first; caneta protege bytes; parar no
checkpoint). Base: `CONSERTO_CP3_REPORT.md` §6 — verificado pela Cowork nos bytes, inclusive o
fato de que $6.96 dos $25.21 foram o ship que caiu sem créditos e perdeu o ledger (padrão que a
alavanca G3 elimina).

**Decisões do operador:** aceite do CP3 registrado; teto desta unit (`_josh_b_replay2`) elevado
a **US$ 35** exclusivamente para concluir a prova do estado salvo (os $25.21 já gastos contam);
o teto de produção continua US$ 25/unit e a unit seguinte o prova do zero.

## G1 — Projeção em lote
`write_cells` e `record_blanks` (plural) na sessão de projeção do ship — mesma semântica e
validação dos singulares (cada célula com valor + citação + confiança próprios; recusa de
fórmula por célula). É o conserto F3 aplicado ao ship. Meta: as ~300 ações restantes em poucas
dezenas de turnos, não 300 chamadas.

## G2 — Projeção com memória em delta
A sessão de projeção recebe: (a) o mapa do template UMA vez; (b) apenas os campos da memória
ainda sem célula correspondente no ledger (os 87 já projetados não voltam ao contexto);
(c) contagens agregadas do resto. Montagem de prompt é plumbing; quem decide célula e valor
continua sendo o modelo.

## G3 — `minorh ship --continuar`
Retomada do ledger salvo (que já persiste por turno): re-abre o DDR existente, pula ações já
aplicadas, continua da primeira pendente. Nunca mais re-projeção do zero após queda. Teste com
queda simulada no meio.

## G4 — Convergir a Josh B do estado salvo
Com G1–G3 no lugar: `MINORH_TETO_UNIT_USD=35 minorh ship --continuar` na `_josh_b_replay2` —
projeção do restante da memória → auditoria de 100% com `gpt-5.6-terra` → correção → regra de
embarque → kit → `_medir.py` final.

**Aceite (fecha a prova da ordem original):**
- toda célula do DDR ou escrita-com-citação ou branca-com-motivo-e-dono (cobertura final
  reportada contra as 2.905 do gabarito, por aba);
- **0 célula reprovada embarcada** (regra de embarque exercitada no corpus real);
- auditoria 100% família B sem carimbo; amostra ≥5 reprovações explicadas (defeito real ×
  calibração, com a página citada);
- os **15 divergentes** e os **6 "escreveu onde a mão não tem"** da medição atual explicados um
  a um no relatório (erro do sistema, erro da mão, ou grão de linha);
- conflito `62 vs 67` confrontado pela auditoria (o denominador 67 já está provado por contagem
  citada);
- hash de fórmulas; kit md5; quarentena com prova persistida TAMBÉM nos ships (a lacuna de
  registro anotada no CP3 fecha aqui: sonda gravada por comando, não só ao fim do driver);
- custo total da unit ≤ $35, por comando; horas de operador registradas via `minorh horas`;
- `CONSERTO_CPG_REPORT.md` + baseline atualizada no `WORKBENCH_STATUS.md`.

## Fora
Nada de replay 3 do zero (a prova do teto de $25 em produção é da PRÓXIMA unit real, com fichas
e cache quentes); nada nas units entregues; achado que não move esta prova → BACKLOG.
