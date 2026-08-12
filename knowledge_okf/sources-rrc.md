---
concept: 'sources: rrc'
type: regra
sources:
- knowledge/rules/sources.yaml
links: []
unit: ''
confidence: herdado da base escrita a mao
---

- **label**: Texas Railroad Commission
- **kind**: portal
- **action**: fetch
- **base_url**: webapps.rrc.texas.gov
- **search_by**:
  - api
  - permit_number
- **navigation**:
  - **wellbore**: ewaMain.do → Wellbore Query → API
  - **drilling_permit**: ewaMain.do → Drilling Permit (W-1) Query → API → permit no.
  - **completion**: ewaMain.do → Completion Query → API
  - **production**: Production Data Query → lease number
  - **plat**: attachment of the W-1, or gis.rrc.texas.gov GIS Viewer
- **forbidden_methods**:

- **known_failure_modes**:
  - The site answers 'application error' for stretches. That is a state of the world, not a failed item: record the attempt with its date and keep the item open — never convert it to unfindable.
- **typical_effort**: 4 documents in roughly one 30-minute sitting
