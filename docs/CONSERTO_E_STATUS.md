# ETAPA E — STATUS INTERROMPIDO (não é o CP3)
**Data:** 2026-08-24 · **Branch:** `conserto-definitivo` · **Executor:** Code
**Bloqueio:** créditos da API Anthropic esgotados no meio da correção do ship do replay
(`anthropic.BadRequestError 400: credit balance is too low`). Só o operador resolve.

## O que rodou (tudo sob quarentena, com prova no log)

`data/units/_josh_b_replay/`: corpus real da Josh B **in-place** (200 zips / 991MB /
1.132 documentos, por hardlink — zero duplicação, original intocado), template real da casa,
populações declaradas ANTES em `POPULACOES.md`, quarentena ativa em todos os comandos
(`_quarentena_prova.json`: 2 bloqueios de sonda por comando, **0 tentativas do run** em todos).

| Passo | Resultado | Custo |
|---|---|---|
| `unidade` | censo **2.715→2.733**; 11 escritos; 3 perguntas de verdade (template com dados de Reeves/Panola; manuscrito 610/245; leases sem pasta) e 5 pedidos em 3 sentadas | $4.5957 |
| operador (Code) | XREF, Lease & Mineral Schedule, Well List e Project Log (existiam no disco) → FILES; P1–P3 respondidas SÓ com registrado (ficha do template, precedente do cartório, manual-7.3); TOs/JOA só existem dentro do kit entregue (gabarito) → **ficam pendentes** | 0.3h |
| `continuar` ×2 | 67 escritos; P1–P3 viradas precedente global; cotejo da P3 feito pelo modelo (leases distintos — não fundiu); brancos cobrindo as ~1.955 células de exemplo do template | $4.1652 + $5.7405 |
| `ship` (1ª) | **bug real achado**: resposta cortada em `max_tokens` sem conteúdo era tratada como "modelo parou" → DDR vazio. Consertado no `run_loop` (instrução de refazer em passos menores, teto de cortes; testado) | $2.1382 |
| `ship` (2ª) | projeção completa (44 turnos, 33 escritas + 43 brancos, hash de fórmulas ok); auditoria rodada 1 (`openai/gpt-5.6-terra`, família B, sem carimbo): **33 auditadas, 16 reprovadas**; a correção morreu no 400 de créditos | $3.1872 (+ ~$0.05–0.10 terra, não persistido — consertado: `vereditos_rodada1.json` agora flui ao disco) |

**Acumulado da unidade: $19.8268** de $25. Horas do operador: 0.3h.

## Medição E3 preliminar (harness fora do run; estado NÃO-final)

Gabarito (DDR à mão): **2.905** células não vazias. Cobertura atual: **26,7%**
(33 por escrita + 742 por branco declarado). Das 33 escritas: 13 concordam, 9 equivalentes,
11 divergem, 0 escritas onde a mão não tem; 102 herdadas do template (não contam);
2.770 caladas. **16 células reprovadas seguem no arquivo** porque a correção não rodou —
o estado atual NÃO satisfaz "0 reprovada embarcada"; é exatamente o que a regra de embarque
removeria ao completar. Artefato: `_minorh/ship/MEDICAO_E3.json`.

## Leitura honesta da trajetória (o número que o doc governante pediu)

- O laço real converge DEVAGAR para uma unidade de 2.905 células: ~$14.5 compraram 67 campos
  provados + os brancos estruturais. Nesta trajetória, ≥90% de cobertura custaria múltiplos
  de $25 — o teto de $25/unit, nesta primeira unit real, **não fecha** com o fluxo atual.
  (A meta era medir na primeira unit real e revisitar com número na mão — este é o número.)
- Gargalos medidos: (a) `continuar` reapresenta ~1.100 docs "novos" a cada ciclo (lido = só o
  aberto via `read_page`); (b) memória campo-a-campo via `gravar_campo` unitário; (c) grande
  parte do corpus é .tif sem camada de texto (OCR pago por página).
- O que JÁ ficou provado nesta etapa: quarentena por identidade com prova; pull list e sentadas
  no dia 1 real; precedentes aplicados sem fusão indevida (P3 cotejada e negada pelo modelo);
  caneta/hash de fórmulas no template real; dois bugs de laço achados e consertados
  (max_tokens truncado; persistência de vereditos).

## O que falta para fechar o CP3 (decisões do operador)

1. **Créditos Anthropic** — recarregar (Plans & Billing). Sem isso nada roda.
2. **Teto**: terminar o ship (re-projeção ~$3.2 + correção + reauditoria + kit) estoura os $25.
   Opções: (a) autorizar exceção `MINORH_TETO_UNIT_USD=<novo>` só para concluir a prova e medir
   o custo real total; (b) aceitar a medição parcial como resultado do CP3 e revisitar o fluxo
   antes de nova rodada (os gargalos acima são endereçáveis por ordem nova).
3. Ao concluir: `compare.py` final, conflito 62 vs 67 pela auditoria, kit completo,
   `CONSERTO_CP3_REPORT.md` e atualização do `WORKBENCH_STATUS.md`.
