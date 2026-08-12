---
concept: transmittal_cover_is_not_the_document/fixture
type: regra
sources:
- knowledge/fixtures/transmittal_cover_is_not_the_document/fixture.yaml
links: []
unit: ''
confidence: herdado da base escrita a mao
---

- **lesson_id**: transmittal_cover_is_not_the_document
- **type**: classificacao
- **scope**: project
- **created**: 2026-08-11
- **source_event**: A cold re-drop classified an Original Title Opinion as correspondence because page 1 was the examiner's transmittal letter ("Dear Mr. B: Enclosed please find our Original Title Opinion"). The fix was applied to title opinions and to nothing else, so it was a fix and not a rule. The generalisation was demanded after a second corpus put thirteen files named "<LESSOR> LSE <lease no>.PDF" through the same reader — there the reader was right (all thirteen really are certified-mail letters from the operator to the lessor), which is precisely why the rule and its counter-case must BOTH be locked: the rule must promote the instrument page when one exists, and must NOT invent one when it does not.

- **statement**: When the front pages of a document all classify as transmittal (correspondence or unidentified), keep reading, bounded, until a page names an instrument. If a page names an instrument, THAT is the document's category, whatever the cover page said. If no page does, the document IS correspondence — the rule never manufactures an instrument. This applies to every category, on the text path and the vision path alike.

- **files**:
  - - **path**: data/fixtures/transmittal_cover_is_not_the_document/to_original_behind_cover_letter.pdf
    - **sha256**: None
    - **role**: cover_then_instrument
  - - **path**: data/fixtures/transmittal_cover_is_not_the_document/lease_behind_cover_letter.tif
    - **sha256**: None
    - **role**: cover_then_instrument
  - - **path**: data/fixtures/transmittal_cover_is_not_the_document/assignment_behind_cover_letter.tif
    - **sha256**: None
    - **role**: cover_then_instrument
  - - **path**: data/fixtures/transmittal_cover_is_not_the_document/probate_behind_cover_letter.pdf
    - **sha256**: None
    - **role**: cover_then_instrument
  - - **path**: data/fixtures/transmittal_cover_is_not_the_document/letter_only_no_instrument.pdf
    - **sha256**: None
    - **role**: must_stay_correspondence
- **cases**:
  - - **name**: title opinion behind its transmittal letter
    - **pages**:
      - correspondence
      - title_opinion
    - **expect**: title_opinion
  - - **name**: lease behind a cover letter
    - **pages**:
      - correspondence
      - lease_ogl
    - **expect**: lease_ogl
  - - **name**: assignment behind a cover letter
    - **pages**:
      - correspondence
      - assignment
    - **expect**: assignment
  - - **name**: probate behind a cover letter
    - **pages**:
      - correspondence
      - probate_heirship
    - **expect**: probate_heirship
  - - **name**: instrument sits deeper than the two-page window
    - **pages**:
      - correspondence
      - correspondence
      - correspondence
      - lease_ogl
    - **expect**: lease_ogl
  - - **name**: a letter with no instrument behind it stays a letter
    - **pages**:
      - correspondence
      - correspondence
    - **expect**: correspondence
  - - **name**: an unidentified page never promotes itself over a letter
    - **pages**:
      - correspondence
      - unplaced
    - **expect**: correspondence
- **synthetic_ok**: True
