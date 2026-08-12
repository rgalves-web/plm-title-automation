---
concept: 'categories: title_opinion'
type: regra
sources:
- knowledge/taxonomy/categories.yaml
links: []
unit: ''
confidence: herdado da base escrita a mao
---

- **label**: Title Opinion
- **feeds**:
  - ownership_report
  - ownership_wells
  - lease_review
- **identity_fields**:
  - abstract
  - gross_acres
  - cert_date
- **relevance_test**: Does the opinion's legal description fall inside the unit perimeter (abstract, and block where the survey is blocked)?

- **disposition_default**: read
- **risk_tier**: high
- **variants**:
  - original
  - supplemental
  - second_supplemental
  - division_order
- **looks_like**: First pages read TITLE OPINION or OPINION OF TITLE, name an examining firm, carry a certification date and a legal description with acreage.

- **precedence**: Per tract, the most recent certification date controls; earlier opinions over the same description are superseded, never merged.

- **proves_terms**:
  - **for_entity**: lease
  - **match_on**:
    - recording_book_page
  - **proves**:
    - lessor
    - lessee
    - instrument_date
    - recording
    - term
    - royalty
    - interest_covered
  - **frame_local**:
    - legal_description
  - **cannot_prove**:
    - bonus
    - depth_limitation
  - **reason_for_unstated_terms**: doc_nao_localizado
  - **also_a_defect**: False
  - **note**: Match by RECORDING, never by lessor name: the same lessor holds leases in several units, and the opinion's schedule is the only place the two can be told apart. A lease the opinion does not schedule gets nothing from it — coverage is not assumed from the opinion being in the folder.
