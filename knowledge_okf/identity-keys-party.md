---
concept: 'identity_keys: party'
type: entidade
sources:
- knowledge/ontology/identity_keys.yaml
links: []
unit: ''
confidence: herdado da base escrita a mao
---

- **required**:
  - name_as_written_in_instrument
- **never_identify_by**:
  - approximate_surname
  - fuzzy_match_score
- **note**: Fuzzy similarity may propose a candidate; it may never confirm one.
