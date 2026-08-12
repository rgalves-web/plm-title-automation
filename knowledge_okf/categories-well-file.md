---
concept: 'categories: well_file'
type: regra
sources:
- knowledge/taxonomy/categories.yaml
links: []
unit: ''
confidence: herdado da base escrita a mao
---

- **label**: Well file (RRC)
- **feeds**:
  - ownership_wells
  - well_files
- **identity_fields**:
  - api
- **relevance_test**: Does the API match the unit's well?
- **disposition_default**: read
- **risk_tier**: low
- **looks_like**: RRC output — W-1 drilling permit, W-2/G-1 completion, wellbore query, production report, plat. May be PDF or CSV.
