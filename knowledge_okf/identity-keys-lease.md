---
concept: 'identity_keys: lease'
type: entidade
sources:
- knowledge/ontology/identity_keys.yaml
links: []
unit: ''
confidence: herdado da base escrita a mao
---

- **required**:
  - eog_lease_number
  - recording_book_page
- **never_identify_by**:
  - lessor_name
- **note**: Both fields or it is a candidate. One alone (number without recording, or recording without number) never promotes to confirmed.
