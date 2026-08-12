---
concept: engagement
type: unidade
sources:
- knowledge/project/engagement.yaml
links: []
unit: ''
confidence: herdado da base escrita a mao
---

- **version**: 1
- **engagement**: BKV122TX
- **fields**:
  - **client**:
    - **value**: BKV
    - **source**: Project Log workbook, titled "BKV122TX - Project Log", tab "OneLine w PV10 (BKV)". The engagement code itself carries the client prefix.

    - **confidence**: stated_by_workbook_title
  - **acquisition**:
    - **value**: Project Emirates
    - **source**: The engagement root folder is named "BKV122TX - Project Emirates" and every client index workbook lives under it. A folder name is a weak source; no document read so far prints the project name. If a stronger source is required, this field reverts to blank.

    - **confidence**: weak_folder_name
  - **operator**:
    - **value**: EOG Resources, Inc.
    - **source**: RRC wellbore query CSVs in the unit corpora (Operator Name = "EOG RESOURCES, INC.") and each unit's recorded designation, executed by EOG Resources, Inc. as lessee-declarant. The per-unit recording citation is added by the round from the unit's own perimeter — a specific Vol/Pg is a unit fact and does not live here (invariant 13).

    - **confidence**: stated_by_document
  - **seller**:
    - **value**: EOG Resources, Inc.
    - **source**: Every lease in the unit's Exhibit "A" names EOG Resources Inc. as lessee; the engagement's due-diligence object is the Seller's leasehold (BPM - Due Diligence (Leasehold).pdf frames the scope as "the Seller's specific interest").

    - **confidence**: stated_by_document
  - **state**:
    - **value**: Texas
    - **source**: Each unit's recorded designation opens "STATE OF TEXAS"; the round cites the unit's own recording when it writes the cell.

    - **confidence**: stated_by_document
  - **counties**:
    - **value**: Montague
    - **source**: The engagement covers Montague County, Texas (CLAUDE.md engagement scope); each unit's recorded designation states "COUNTY OF MONTAGUE" and the RRC wellbore queries return County = MONTAGUE. Per-unit recording citations come from the round.

    - **confidence**: stated_by_document
  - **dsu_str**: None
