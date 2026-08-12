---
concept: 'exclusion_reasons: duplicata'
type: regra
sources:
- knowledge/rules/exclusion_reasons.yaml
links: []
unit: ''
confidence: herdado da base escrita a mao
---

- **label**: Duplicate of a document already placed
- **applies_to**:
  - skip
  - unplaced
- **definition**: Byte-identical to a document already classified.
- **requires**:
  - duplicate_of
