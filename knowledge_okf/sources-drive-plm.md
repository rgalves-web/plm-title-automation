---
concept: 'sources: drive_plm'
type: regra
sources:
- knowledge/rules/sources.yaml
links: []
unit: ''
confidence: herdado da base escrita a mao
---

- **label**: PLM Drive
- **kind**: repository
- **action**: fetch
- **search_by**:
  - eog_lease_number
  - contract_number
  - title_opinion_number
- **navigation**:
  - **primary**: lease folder named by the EOG lease number
  - **fallback_siblings**: numerically adjacent lease folders — a document is often filed in a sibling folder of the same series

  - **fallback_neighbouring_units**: folders of NEIGHBOURING UNITS that touch the same tract: a title opinion for a shared tract is commonly filed under whichever unit ordered it

- **forbidden_methods**:
  - - **method**: lessor_name
    - **why**: Lessors hold leases in many units. A name search returns other units' leases that look right and are not; the key is the pair EOG lease number + recording (volume/page).
- **typical_effort**: immediate when the folder exists; otherwise the siblings and neighbouring units are the productive path
