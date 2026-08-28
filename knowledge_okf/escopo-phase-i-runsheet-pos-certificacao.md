---
concept: escopo phase i runsheet pos certificacao
type: regra-cliente
sources:
- ordem CODE_INSTRUCTIONS_ETAPA_H (28/08/2026) — lições da rodada manual da Webb B
- 'gabarito Webb B: Runsheet 27 itens, todos pós-certificação (certs 25/01–08/02/2012)'
links: []
unit: ''
confidence: ''
---

## H1 — O escopo vem do spec, e o Runsheet é PÓS-certificação

A maior perda da rodada manual da Webb B (4 horas) foi abrir cadeia pré-2012 que o spec exclui. Invariante de ESCOPO, aplicado pelo modelo e conferido pelo Auditor, nunca por `if`:

1. Antes de qualquer projeção, ler o spec de submissão e escrever `ESCOPO.md` no estado da unit (`declarar_escopo`): o que entra em cada aba, a data de certificação de CADA TO, e a regra **"Runsheet = instrumentos protocolados APÓS a última certificação"**. O operador aceita o ESCOPO.md antes de o ship começar (`minorh escopo aceitar`).
2. Todo item de runsheet carrega a data que o qualifica. Item sem data pós-certificação NÃO embarca — vira linha do relatório de fora-de-escopo, não do DDR.
3. Achado fora de escopo não é lixo nem vira trabalho: vai para `FORA DO ESCOPO PHASE I/` com um índice de uma página, e o ship segue.
