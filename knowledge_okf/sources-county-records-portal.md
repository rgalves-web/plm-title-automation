---
concept: 'sources: county_records_portal'
type: regra
sources:
- knowledge/rules/sources.yaml
links: []
unit: ''
confidence: herdado da base escrita a mao
---

- **label**: TexasFile / CourthouseDirect
- **kind**: portal
- **action**: fetch
- **search_by**:
  - grantor_name
  - grantee_name
  - date_window
  - book_page
- **navigation**: county → grantor/grantee index → name + date window → document
- **forbidden_methods**:
  - - **method**: abstract
    - **why**: The abstract filter silently drops recorded instruments. Searching by abstract returns a short, confident, WRONG list.
- **method_note**: Search by NAME plus a date window, then sift the reduced list by survey/block by eye. A known volume/page makes it a direct lookup.

- **typical_effort**: leases with a known Vol/Pg come out in one sitting
