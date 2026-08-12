---
concept: resolver_identity_by_key/fixture
type: regra
sources:
- knowledge/fixtures/resolver_identity_by_key/fixture.yaml
links: []
unit: ''
confidence: herdado da base escrita a mao
---

- **lesson_id**: resolver_identity_by_key
- **type**: identidade
- **scope**: project
- **created**: 2026-08-11
- **source_event**: A source-truth replay reported eight Ownership MI cells as CONFIRMED against a title opinion whose abstract differed from the one the audit citation named. The values were non-distinctive fractions, so the wrong document's text "confirmed" them. Two causes: the citation was read as a filesystem path, so a date inside it collapsed the whole citation to a year; and the fallback match returned whichever candidate the directory walk hit first, which made resolution depend on folder layout.

- **statement**: Resolve a citation to a document by its identity key (title opinion = abstract + gross acres + certification date). Text similarity may propose a candidate; it may never confirm one across a differing abstract. Byte-identical copies of one document are one identity; same name with differing bytes is not.

- **files**:
  - - **path**: data/fixtures/resolver_identity_by_key/T-O SUPP UNIT A-227 141.5AC (cert 10-18-2008).pdf
    - **sha256**: None
    - **role**: expected_target
  - - **path**: data/fixtures/resolver_identity_by_key/T-O FIRST SUPP UNIT A-682 146.5AC (issued 07-11-2008).pdf
    - **sha256**: None
    - **role**: must_not_match
- **cases**:
  - - **citation**: T-O SUPP Unit A-227 141.5 ac (T0140210), cert. 10/18/2008
    - **expect_abstract**: 227
    - **must_not_resolve_to_abstract**: 682
  - - **citation**: T-O FIRST SUPP Unit A-682 146.5 ac (issued 07-11-2008)
    - **expect_abstract**: 682
    - **must_not_resolve_to_abstract**: 227
- **synthetic_ok**: True
