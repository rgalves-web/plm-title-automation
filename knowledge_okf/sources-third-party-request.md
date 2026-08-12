---
concept: 'sources: third_party_request'
type: regra
sources:
- knowledge/rules/sources.yaml
links: []
unit: ''
confidence: herdado da base escrita a mao
---

- **label**: Third party (Clerk, Seller, examining attorney)
- **kind**: request
- **action**: request
- **search_by**:

- **navigation**: identify the holder, the channel, the cost and the turnaround
- **forbidden_methods**:
  - - **method**: portal_search
    - **why**: Treating a request as if it were findable in a portal burns sessions and leaves the item open forever. Nobody can search their way to a document that only a person can hand over.
- **requires_for_each_item**:
  - who
  - channel
  - cost
  - expected_turnaround
- **method_note**: Probate is filed where the DECEDENT's estate was administered, which is often NOT the county the minerals sit in. The identity is the cause number plus its county.
