---
concept: 'categories: dpu_amendment'
type: regra
sources:
- knowledge/taxonomy/categories.yaml
links: []
unit: ''
confidence: herdado da base escrita a mao
---

- **label**: DPU amendment
- **feeds**:
  - unit_and_pooling_agreements
  - perimeter
- **identity_fields**:
  - recording_book_page
  - effective_date
- **relevance_test**: Does it amend this unit's own designation?
- **disposition_default**: read
- **risk_tier**: high
