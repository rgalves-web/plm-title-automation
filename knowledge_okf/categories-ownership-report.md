---
concept: 'categories: ownership_report'
type: regra
sources:
- knowledge/taxonomy/categories.yaml
links: []
unit: ''
confidence: herdado da base escrita a mao
---

- **label**: Ownership report (AFD/MOR)
- **feeds**:
  - ownership_report
- **identity_fields**:
  - lease_number
- **relevance_test**: Is the tract it reports part of the unit per the DPU?
- **disposition_default**: read
- **risk_tier**: high
- **looks_like**: A per-lease ownership schedule produced by the seller, not an attorney.
- **precedence**: Used for a tract only where no title opinion covers it.
