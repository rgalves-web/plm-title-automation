---
concept: 'categories: dpu'
type: regra
sources:
- knowledge/taxonomy/categories.yaml
links: []
unit: ''
confidence: herdado da base escrita a mao
---

- **label**: Declaration of Pooled Unit
- **feeds**:
  - unit_and_pooling_agreements
  - perimeter
- **identity_fields**:
  - recording_book_page
  - effective_date
- **relevance_test**: Does its book.page match the unit's own designation?
- **disposition_default**: read
- **risk_tier**: high
- **looks_like**: Recorded declaration/designation naming the unit, with an Exhibit "A" listing leases and an exhibit plat.

- **authority**: Exhibit "A" is the authority on which leases are in the unit. Every other index (XREF, schedule) is cross-checked AGAINST it; a divergence is a finding, never a silent preference.

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
  - **cannot_prove**:
    - royalty
    - term
    - bonus
    - pooling_clause
    - shut_in
    - depth_limitation
    - legal_description
  - **reason_for_unstated_terms**: doc_nao_localizado
  - **also_a_defect**: False
