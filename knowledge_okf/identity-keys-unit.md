---
concept: 'identity_keys: unit'
type: entidade
sources:
- knowledge/ontology/identity_keys.yaml
links: []
unit: ''
confidence: herdado da base escrita a mao
---

- **required**:
  - dpu_book_page
  - effective_date
- **never_identify_by**:
  - name
- **note**: A unit whose name merely prefixes another's is not that other unit. The recorded DPU book.page plus its effective date is what makes a unit that unit.
