---
concept: 'categories: lease_memorandum'
type: regra
sources:
- knowledge/taxonomy/categories.yaml
links: []
unit: ''
confidence: herdado da base escrita a mao
---

- **label**: Memorandum of lease
- **feeds**:
  - lease_review
  - potential_defects
- **identity_fields**:
  - eog_lease_number
  - recording_book_page
- **relevance_test**: Same pair test as the lease it memorialises.
- **disposition_default**: read
- **risk_tier**: high
- **looks_like**: Short-form recorded instrument that memorialises a lease: parties, date, description and term, usually without royalty or the full clause set.

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
  - **cannot_prove**:
    - royalty
    - bonus
    - pooling_clause
    - shut_in
    - depth_limitation
  - **reason_for_unstated_terms**: doc_nao_localizado
  - **also_a_defect**: True
  - **defect_label**: MISSING LEASE
  - **note**: The memorandum was the first case of this rule, and for a while it was written as if it were the only one. It is not: what makes it a source is being of record and declaring the term, not being a memorandum.

- **dual_disposition**:
  - **as_source**: The recorded memorandum IS the of-record source for the terms it actually states — those cells are filled and cited to it, at its page.

  - **as_defect**: A lease whose only record is a memorandum is ALSO reported as a MISSING LEASE under Potential Defects, with the complete instrument requested from the Seller.

  - **terms_it_cannot_prove**: Any term the memorandum does not state stays blank with a named reason from the vocabulary — never inferred from the memorandum's silence.

  - **reason_for_unstated_terms**: doc_nao_localizado
  - **defect_label**: MISSING LEASE
