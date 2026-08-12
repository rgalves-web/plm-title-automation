---
concept: 'exclusion_reasons: pendente_de_terceiro'
type: regra
sources:
- knowledge/rules/exclusion_reasons.yaml
links: []
unit: ''
confidence: herdado da base escrita a mao
---

- **label**: Pending a third party
- **applies_to**:
  - blank
  - pending
- **definition**: Awaiting the seller, the client, an examiner or a courthouse. Carries who was asked and when.

- **requires**:
  - asked_of
  - asked_on
