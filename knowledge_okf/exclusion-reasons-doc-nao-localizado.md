---
concept: 'exclusion_reasons: doc_nao_localizado'
type: regra
sources:
- knowledge/rules/exclusion_reasons.yaml
links: []
unit: ''
confidence: herdado da base escrita a mao
---

- **label**: Document not located
- **applies_to**:
  - blank
  - unplaced
  - pending
- **definition**: The document is named and searched for, and is not in the file. Carries the hunt: where we looked and with what search terms.

- **requires**:
  - hunt_log
