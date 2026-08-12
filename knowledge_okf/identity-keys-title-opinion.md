---
concept: 'identity_keys: title_opinion'
type: entidade
sources:
- knowledge/ontology/identity_keys.yaml
links: []
unit: ''
confidence: herdado da base escrita a mao
---

- **required**:
  - abstract
  - gross_acres
  - cert_date
- **never_identify_by**:
  - filename
- **note**: This is the key the 2026-08-11 resolver finding calls for: a citation already carries abstract + acreage + opinion number + cert date, so it should be parsed into this key and resolved by key — not matched as text.
