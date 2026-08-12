---
concept: 'exclusion_reasons: fora_do_perimetro'
type: regra
sources:
- knowledge/rules/exclusion_reasons.yaml
links: []
unit: ''
confidence: herdado da base escrita a mao
---

- **label**: Outside the unit perimeter
- **applies_to**:
  - skip
  - unplaced
  - blank
- **definition**: The document's abstract, tract or lease is not in the unit perimeter derived from the DPU Exhibit "A".
