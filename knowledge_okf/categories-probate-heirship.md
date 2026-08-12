---
concept: 'categories: probate_heirship'
type: regra
sources:
- knowledge/taxonomy/categories.yaml
links: []
unit: ''
confidence: herdado da base escrita a mao
---

- **label**: Probate / affidavit of heirship
- **feeds**:
  - runsheet
  - outstanding_curative
- **identity_fields**:
  - recording_book_page
- **alternate_identity_fields**:
  - cause_number
  - county
- **relevance_test**: Does it touch a party in the unit's chain of title?
- **disposition_default**: read
- **risk_tier**: high
- **looks_like**: Probate proceedings, wills, or affidavits of heirship. May be filed in a county other than the one the minerals sit in — the cause number and its county are then the identity.
