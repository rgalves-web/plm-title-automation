---
concept: auditoria celulas ordinais sao estrutura
type: regra
sources:
- AUDITORIA_OPENAI.json da _cp1_sintetica (24/08/2026)
- decisão do operador no aceite do CP2 (24/08/2026)
links: []
unit: ''
confidence: ''
---

## Célula ordinal é ESTRUTURA do artefato, não fato de title

Células cujo valor é número de ordem/sequência — nº da linha do Curative ("1", "2"), "NO." do Runsheet, o L# de um lease na ordem do Lease Review, numeração de item — não afirmam nada sobre o registro público. O documento citado não "sustenta" um ordinal, porque o ordinal nasce do ARQUIVO, não da página.

**Julgamento correto do auditor:** a célula é aprovada se (a) a ordem/contagem é consistente com o restante do arquivo (o item "2" é de fato o segundo da sequência; a contagem bate com as linhas vizinhas) e (b) a página citada não a contradiz. Reprovar um ordinal "porque a página cita cinco leases" é julgar estrutura como fato.

**Origem (achado de calibração, 24/08/2026):** no exercício do ramo B da sintética (`AUDITORIA_OPENAI.json`), o auditor OpenAI reprovou `Curative!A3` — um nº de ordem — exatamente por esse desvio; o operador decidiu NÃO reabrir o kit e mandou calibrar. O que é ou não ordinal é decisão do auditor caso a caso — esta ficha dá o critério, nenhum código inspeciona valor.
