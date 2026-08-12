---
concept: 'sources: county_clerk_records'
type: regra
sources:
- knowledge/rules/sources.yaml
links: []
unit: ''
confidence: herdado da base escrita a mao
---

- **label**: County Clerk — real property records
- **kind**: courthouse
- **action**: fetch
- **search_by**:
  - book_page
  - instrument_number
- **navigation**: real property records of the county where the land sits, by volume/page
- **forbidden_methods**:

- **method_note**: Direct lookup by recording reference. Note that MINERALS and PROBATE can sit in different counties — see third_party_request.
