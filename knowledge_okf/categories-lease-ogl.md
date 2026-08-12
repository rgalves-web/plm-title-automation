---
concept: 'categories: lease_ogl'
type: regra
sources:
- knowledge/taxonomy/categories.yaml
links: []
unit: ''
confidence: herdado da base escrita a mao
---

- **label**: Oil, gas and mineral lease
- **feeds**:
  - lease_review
  - ownership_report
- **identity_fields**:
  - eog_lease_number
  - recording_book_page
- **relevance_test**: Does the pair (lease number, recording) appear in the DPU Exhibit "A"? Neither field alone decides.

- **disposition_default**: read
- **risk_tier**: high
- **looks_like**: Recorded OGML naming lessor and lessee, with term, royalty and description.
- **proves_terms**:
  - **for_entity**: lease
  - **match_on**:
    - recording_book_page
    - eog_lease_number
  - **proves**:
    - lessor
    - lessee
    - instrument_date
    - recording
    - legal_description
    - term
    - royalty
    - bonus
    - pooling_clause
    - shut_in
    - depth_limitation
    - interest_covered
  - **cannot_prove**:

  - **reason_for_unstated_terms**: doc_nao_localizado
  - **also_a_defect**: False
