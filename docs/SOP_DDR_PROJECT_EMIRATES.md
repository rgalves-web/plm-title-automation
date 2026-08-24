# SOP — DDR / Project Emirates (consolidado do Slack, 14/08/2026)
_Fonte: canais, threads e DMs do Slack da PLM, consolidados pelo operador. Instrução mais nova controla. Este documento é METODOLOGIA do cliente — vale para todas as unidades do BKV122TX e deve virar precedente global._

## 1. Establish scope
- One DDR per assigned unit, even where several title opinions cover different tracts. Organize the runsheet by TO or tract if useful; do not create separate DDRs per tract. [Slack Aug 12]
- Confirm the assigned unit and wells in the project log. Do not include unassigned wells merely because they appear on the RRC. [Slack Jul 30]
- Start with the DPU/unit designation and amendments. Use the lease exhibit to identify the unit's leases, then reconcile against BOTH sheets of the Lease-to-Well XREF and the TOs.
- Use the TOs identified in Column G of the project log. Verify whether all DPU tracts have TO coverage.

## 2. Identify every lease that must be reported
- Filter both XREF sheets for the unit and reconcile against the DPU and amendments.
- Every seller-represented lease associated with the unit must appear in BOTH: Ownership Report and Lease Review.
- Do not submit until every applicable XREF lease is accounted for. [Slack Aug 11]
- If an amendment removes a lease from the unit, exclude it from the DDR; consider explaining the removal in the Summary. [Slack Aug 11]

## 3. Supplemental runsheet
Run title from the controlling TO certification date through the latest available recorded date:
- Use the EARLIEST certification date where multiple TOs provide overlapping coverage.
- Run EOG/seller forward for every instrument affecting the unit or leasehold.
- Run unleased mineral owners and other WI owners forward (did EOG later acquire?).
- For a post-TO lease: (1) TO's unleased mineral owner forward; (2) later lessor backward from lease date to TO cert date; (3) lessee forward into EOG.
- Post-certification instruments satisfying TO requirements go on the runsheet; mark the requirement satisfied.
- Place a copy of EVERY runsheet instrument in `Title Documents`, labeled `volume.page`. [Slack Jul 21]

## 4. Ownership
- Enter every applicable seller-represented lease from both XREF sheets.
- TO Lease Analysis is the starting point; update for supplemental-title activity.
- Compare verified WI/NRI against seller's represented WI/NRI in `Well List – Prelim AV%`.
- **NEVER hard-key or overwrite blue formula cells.** Verified inputs go in white cells; formulas compute lease and unit totals. [Slack Aug 13 — controlling]
- Auto-fit row heights.

## 5. Lease Review
- Every seller-represented lease from the XREF/DPU reconciliation.
- Populate provisions from TO, full OGL, amendments, seller's lease files.
- Memorandum-only: enter what the memo provides; leave royalty/other unavailable terms blank; add full OGL to Missing Files; explain in Summary.
- Omission from the TO does NOT mean outside TO coverage — research the chain before treating as uncovered. [Slack Aug 11]

## 6. Missing Files log (controlling, Aug 14)
- List a lease file when the XREF identifies it but (1) no lease folder exists on Drive, or (2) the folder lacks the full OGL.
- Search county records / TexasFile / CourthouseDirect BEFORE concluding a document is unavailable.
- If county records provide it, do not leave a misleading "could not be located" note — the log identifies the actual remaining Drive/client-file deficiency.
- Include genuinely missing TOs, empty TO folders, missing DPUs, probate materials, and other documents necessary to verify title.
- Remove a request when the document is subsequently found and confirmed.
- Also disclose material missing items and their consequences in the DDR Summary. [DM Aug 10]

## 7. Title opinions and curative (PLM Title Review)
- Use the TO's ownership certification "as of" date, NOT necessarily the date printed at the top.
- Use the unit's legal description.
- Separate TO Summary table per original/supplemental TO: opinion type, law firm, operator, cert date, covered legal.
- Report only MATERIAL, CURABLE outstanding requirements that remain unsatisfied after supplemental research.
- Do not elevate requirements marked "Advisory only".
- Later-recorded evidence satisfying a requirement → runsheet + requirement satisfied. [Checklist Jul 16]

## 8. Production and wells
- Texas RRC GIS/viewer. Most recent W-1; older permits/production logs generally unnecessary.
- Review production from completion THROUGH PRESENT; identify and note every zero-production period or gap. [Slack Jul 13]
- `Ownership – Wells`: verified unit WI/NRI from Ownership Report; represented PSA figures from the project log.

## 9. Remaining tabs
- `Agreements`: JOAs and farmouts; none found → `N/A` and dashes in Column B.
- `Unit and Pooling Agreements`: DPU + amendments (notes or separate amendment tables).
- `Disclaimer`: replace `ABC, LLC` with **`BKV Corp.`**
- `Summary`: Client **BKV Corp.** · Acquisition **Project Emirates** · Operator EOG or per project log · Potential Defects = matters causing verified seller interest LOWER than represented · Outstanding Curative = unresolved material requirements · Liens and Encumbrances = mortgages/liens/judgments/DOTs affecting seller interest · Section Notes = missing full leases, TO-coverage limits, ownership discrepancies, production gaps, other client-facing issues.

## 10. Format, package, submit
- Downloaded copy of the template — never edit the master.
- Times New Roman 10pt; center cells horizontally and vertically; remove hard returns from runsheet cells; preserve formulas, borders, headers, styling; update headers for the correct unit/survey; spell-check; auto-fit rows.
- Folder structure (Jul 21, controlling):
```
PLM Reports/
└── [Unit Name exactly as Column E, normal capitalization]/
    └── 1. Landman Submitted/
        ├── Leases/
        ├── PLM Report/
        ├── Seller's Files/
        ├── Title Documents/
        ├── Title Opinions/
        ├── Unit Designation/
        └── Well Files/
```
- Leases: relevant leases and amendments · PLM Report: the DDR · Seller's Files: only relevant supporting files, no mass uploads · Title Documents: every supplemental runsheet instrument · Title Opinions: one copy of each unique TO, no duplicates · Unit Designation: DPU + all amendments · Well Files: applicable RRC production support.
- Notify Trevor in the main BKV channel on submission. Corrections: no reviewer assigned → correct directly; reviewer assigned → contact the reviewer first. [Slack Aug 11]
