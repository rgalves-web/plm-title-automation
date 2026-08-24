---
concept: manual 12 producao e well data
type: regra-cliente
sources:
- Manual Técnico v1.0 (16/08/2026) cap. 12
- docs/SOP_DDR_PROJECT_EMIRATES.md (14/08/2026) §8
- ingerida em 23/08/2026 (ordem CONSERTO_DEFINITIVO, etapa A2)
links: []
unit: ''
confidence: ''
---

## Produção e well data

- Só wells explicitamente atribuídos no project log (S09, 30/07).
- W-1 MAIS RECENTE para spud/completion; não carregar permits antigos sem necessidade.
- Histórico de produção da COMPLETION DATE até o período mais recente (S08, 13/07) — não é "só um ano".
- Classificar separadamente: valor 0 = ZERO_PRODUCTION (registrar intervalo e analisar); campo vazio = MISSING_DATA (NUNCA equiparar a zero); pré-completion = fora da detecção; poço inativo com evidência = STATUS_EXPLAINED; RRC fora do ar = SOURCE_UNAVAILABLE (registrar tentativas).
- Gaps confirmados → Ownership – Wells e, se relevantes, Summary/Section Notes. Se produção zero é defeito ou shut-in documentado é JULGAMENTO do Examinador com precedente — ficha, não código.
