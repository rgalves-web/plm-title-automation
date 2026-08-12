---
concept: 'exclusion_reasons: identidade_ambigua'
type: regra
sources:
- knowledge/rules/exclusion_reasons.yaml
links: []
unit: ''
confidence: herdado da base escrita a mao
---

- **label**: Ambiguous identity
- **applies_to**:
  - unplaced
  - pending
- **definition**: More than one candidate fits and no key distinguishes them; or a required identity field is missing. Never resolved by guessing.

- **requires**:
  - candidates
