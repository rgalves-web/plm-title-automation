---
concept: 'exclusion_reasons: captura_de_tela'
type: regra
sources:
- knowledge/rules/exclusion_reasons.yaml
links: []
unit: ''
confidence: herdado da base escrita a mao
---

- **label**: Screen capture — evidence of a document, not the document
- **applies_to**:
  - skip
  - blank
- **definition**: A photograph or screenshot of a record. It carries no file stamp, no page and cannot be re-read by whoever checks the value later, so it may not be the source of a value that reaches the client. The document itself has to arrive; until it does, the cell is blank with this reason and a brief item names who fetches it.
