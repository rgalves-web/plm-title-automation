# Full System Assessment — PLM Title Automation
**Date of assessment:** 2026-07-01
**Repo:** `C:\Users\Renato\PURPLE LAND MGMT\plm-title-automation`
**Purpose of this document:** independent, no-spin inventory of what the system does, does not do, and how far the deliverable (DDR) is from what the client/team actually needs — for review by another Claude instance or a human.

---

## 1. Project context

**Engagement:** BKV122TX — "Project Emirates". PLM (Purple Land Management) is performing confirmatory title / due diligence for **EOG Resources Inc.** as Seller, across **~300 acquisition units** in **Montague County, Texas**, covering **365 PDP wellbores**.

**Two distinct workstreams exist in this repo:**
1. **MOR** (Master Ownership Report / runsheet) — an older, more mature pipeline that classifies a flat document list and builds an ownership runsheet. Not the current focus but still present and tested.
2. **DD** (Due Diligence) — the workstream this assessment is about. Built from scratch this cycle to support the Project Emirates engagement. Produces a per-unit "DDR" (Due Diligence Report) Excel deliverable from a DDR template.

**Landman process (from actual team call transcript, 2026-07-01, Trevor Dahl leading):**
1. Find your assigned unit in the Project Log (column E).
2. Filter "Lease to Well XREF" by unit name to find the leases belonging to that unit.
3. Cross-reference those leases against the unit's **Declaration of Pooled Unit / Designation of Unit** (Exhibit A) to confirm which leases actually belong to the unit.
4. Copy each lease's file/lease number, search Google Drive, open the lease's folder — it contains many files, most irrelevant (internal, non-recorded paperwork).
5. Inside that folder, find the file starting with "T-O" (Title Opinion). If there is an Original + one or more Supplements covering the **same legal description**, use the **most recent by certification date** as the starting point — earlier ones are superseded.
6. Run supplemental title (chain of title) from that opinion's certification date to present day, limited to instruments affecting the Seller's (EOG's) interest.
7. Consolidate everything into **one run sheet per unit** with three date columns: effective date, instrument date, recorded date.
8. Lease Review tab is explicitly **lower priority** — "run sheet first, lease review later" (Trevor Dahl, 00:44:08).
9. Missing title opinions / lease folders not yet uploaded (client sent 100+ GB via hard drive, still uploading as of the call) is **expected and normal**, not a failure — landmen are told to set those leases aside.

This transcript is important: it validates several of the system's core design choices (see §5) and reveals gaps that were not previously visible in the written instructions alone (see §6).

---

## 2. Architecture — what exists

```
src/dd/
  manifest.py            Pydantic models: UnitManifest, TitleOpinionRef, LeaseRef,
                          ReferenceContractRef, WellRef, RepresentedInterest
  manifest_builder.py     Builds a UnitManifest from 3 client workbooks
                          (Project Log, Lease-to-Well XREF, Well List) for ONE unit
  intake_router.py        Routes a flat pile of uploaded files (xlsx + PDFs, incl.
                          zips) into typed inputs; lite-mode fallback with no
                          reference workbooks
  title_opinion_parser.py LLM-based (Claude, tool-use) structured extraction from
                          one Title Opinion PDF -> TitleOpinionExtraction
  unit_aggregation.py     Deterministic Fraction-based WI/NRI math + reconciliation
                          vs. Well List's declared interest
  dd_pipeline.py          Orchestrator: manifest -> parse TOs -> resolve controlling
                          cert date -> scope-filter supplemental docs -> aggregate ->
                          reconcile -> write DDR
  ddr_writer.py           openpyxl template-filling for all DDR tabs + audit trail
  dd_upload_runner.py     Entry point for the Streamlit UI's "RUN" button

app.py                    3-screen Streamlit frontend (Input / Progress / Complete)
tests/test_dd_*.py        127 tests total across MOR+DD (all passing as of this
                          assessment)
```

**Data flow for one unit:**

```
Project Log + Lease-to-Well XREF + Well List (3 xlsx)
        │
        ▼
manifest_builder.build_manifest(unit_name)
        │  → UnitManifest: seller, county, state, leases[], title_opinions[],
        │    wells[], represented_interest (WI/NRI from Well List)
        ▼
[optional] set_title_opinions_from_uploads()
        │  → overrides XREF-derived TO list with analyst-uploaded PDFs,
        │    bound directly to this unit (bypasses filename-matching entirely)
        ▼
title_opinion_parser.parse_title_opinion() × N   (Claude tool-use, OCR'd text)
        │  → TitleOpinionExtraction per TO: tracts[], each with mineral/royalty/
        │    ORRI owners, working-interest table, leases[], cert date, gross acres
        ▼
dd_pipeline.resolve_controlling_certification_date()
        │  → latest cert date among confirm_coverage=True, successfully-parsed TOs
        │    — hard stop (raises) if none resolve
        ▼
dd_pipeline.select_ownership_basis()
        │  → newest-first walk of TOs; picks the first whose de-duplicated tracts
        │    yield BOTH parseable Seller WI/NRI AND resolvable gross acreage;
        │    de-dupes tracts that are the same land re-stated (over-segmentation)
        ▼
dd_pipeline.apply_supplemental_scope_filter()  (if supplemental doc list supplied)
        │  → REDLINEs anything pre-dating cert date or not touching Seller
        ▼
unit_aggregation.run_dd_aggregation()
        │  → Fraction arithmetic: company_net_acres, net_revenue_acres, computed
        │    Seller WI/NRI, delta vs. Well List's declared WI/NRI, PASS/WARNING/
        │    NOT_COMPUTED status
        ▼
dd_pipeline.build_review_flags()
        │  → assembles human-verification prompts (reconciliation mismatch,
        │    missing TO PDFs, parse errors, acreage provenance, survey caveat)
        ▼
ddr_writer.fill_ddr_template()
        │  → writes Summary, Ownership Report, Ownership - Wells, Lease Review,
        │    Runsheet, PLM Title Review, Agreements, Unit and Pooling Agreements,
        │    DD_Audit_Trail tabs into a copy of the client's own DDR template
```

---

## 3. What works today — verified by an actual end-to-end run

On 2026-07-01, the pipeline was run against real client files for **BOWEN A UNIT**:
`BKV122TX - Project Log.xlsx`, `Lease to Well XREF.xlsx`, `Well List with Prelim AV% directional estimates.xlsx`, `DDR - Template (PLM).xlsx`, and 3 real Title Opinion PDFs (`T-O ORIG…`, `T-O SUPP…`, `T-O SECOND SUPP…`, all covering the same 119.2-acre Samuel Cable Survey A-1449 tract).

**Confirmed working, with real output:**

| Capability | Evidence |
|---|---|
| Single-unit filtering (not all 300 units) | Unit Name field in UI now filters `run_dd_upload` to exactly one unit before the pipeline loop runs |
| Descriptive-filename TO PDFs bound to a unit | `T-O ORIG BOWEN A-1449 119.2 AC.PDF` (no XREF file-number prefix) correctly routed and parsed via `set_title_opinions_from_uploads` |
| Multi-part/zipped TO PDFs | Zip extraction prefixes members with the zip's own T0##### number; multi-part PDFs are merged via PyMuPDF before parsing |
| LLM extraction of TO content | All 3 real PDFs parsed: certification dates, legal descriptions, WI/NRI tables, lease blocks, requirements — via Claude tool-use, cached |
| Certification-date parsing robustness | `"December 11, 2012, at 5:00 p.m."` now parses correctly (was silently dropped, causing a wrong controlling date) |
| Controlling opinion selection with supersession | 3 TOs covering the same tract (Original 2008 → Supp 2008 → Second Supp 2012) correctly collapse to a single controlling basis |
| Tract de-duplication | Second Supp PDF was over-segmented by the LLM into 3 copies of the same 119.2-acre tract; de-dup collapsed them to 1 (was inflating gross acres to 357.6) |
| Gross-acreage derivation from TO text | 119.2 acres extracted from legal description, used as `unit_gross_acres` denominator — no manual entry required |
| WI/NRI aggregation (exact Fraction math) | Computed leasehold WI 0.625 / NRI ~0.5598 from the controlling TO |
| WI/NRI reconciliation vs. Well List | Declared wellbore WI 0.9975 / NRI 0.78813617 compared against computed; WARNING (not silently PASS, not NOT_COMPUTED) |
| Ownership Report tab populated | 32 lease/tract rows with lessor/lessee/royalty/dates from XREF + TOs |
| Ownership - Wells tab populated | BOWEN A UNIT #1H, #2H with API/depth/dates from Well List; template sample rows (`*** E&P LLC`) fully cleared |
| Lease Review tab populated | 32 rows, matched against TO lease blocks where fuzzy-name match succeeds |
| PLM Title Review tab populated | 3 TO summary cards with certification dates, legal descriptions, requirements |
| Runsheet tab | Correct unit/county in title (was leaking template's "Reeves County" sample text), correct scope note with resolved cert date, sample rows cleared |
| Summary tab review flags | Potential Defects / Outstanding Curative Requirements / Section Notes now populated with specific, actionable text (see §4) instead of "--" |
| DD_Audit_Trail tab | Cell-level provenance (sheet, location, source type, source reference, confidence) for every written value |
| Template structural integrity | `_build_template_integrity_report` confirms no unintended formatting/formula breakage on save |
| Test suite | 127/127 passing after all changes described in this document |

---

## 4. The Summary-tab review flags — what they actually say right now

This is the mechanism added to surface "needs manual verification" directly inside the deliverable rather than as a separate report. For BOWEN A UNIT, the generated file currently reads:

> **Potential Defect(s):**
> Computed leasehold WI 0.6250 / NRI 0.5578 (from title opinion [file]) does NOT match represented wellbore WI 0.9975 / NRI 0.7881 (Well List). This gap is typically the JOA / non-consent uplift — confirm against the Joint Operating Agreement(s) on the Agreements tab before relying on either figure.
>
> **Outstanding Curative Requirements:**
> • The Lease-to-Well XREF lists 9 title opinion file numbers for this unit; 3 PDF(s) were provided and parsed. Confirm every tract opinion is accounted for and obtain any missing PDFs.
> • Run supplemental title on EOG RESOURCES INC in MONTAGUE County from 2012-12-11 (controlling certification date) to present.
>
> **Section Notes:**
> • Ownership basis: title opinion [file] (certified [date]). Unit gross acres (119.2) derived from the title opinion legal description — verify against an independent survey/plat.
> • Acreage, boundaries and on-the-ground location are not certified here and require an independent survey.

**Important nuance confirmed by the team call:** a WI/NRI mismatch between leasehold (title-derived) and wellbore (Well List-declared) interest is **expected, not a defect**, when a JOA exists — EOG's wellbore interest is typically higher because it earned non-consenting parties' interest by operating. The flag text above already says this, but it is worth an outside reviewer double-checking that the phrasing doesn't read as an alarm when it is actually routine.

---

## 5. Where the system matches the team's actual process (validated by transcript)

- **Controlling opinion = most recent by cert date among opinions covering the same legal description.** Exactly Trevor Dahl's guidance to Joshua Granada (00:45:15) about "first supplemental" / "second supplemental" opinions being the correct starting point.
- **Supplemental scope = certification date to present, nothing earlier.** Matches Trevor's answer to Juan Rodriguez (00:42:39).
- **One consolidated run sheet per unit**, not one per title opinion. Matches Trevor's answer to Ginger Bolinger (00:52:07).
- **Three run sheet date columns** (effective / instrument / recorded). Matches the template requirement Trevor cites at 00:53:39.
- **Scope limited to the assigned unit only**, discard leases that are shared with other units. Matches Trevor's answer to Raquel Rocha (00:27:08) and the system's `confirm_coverage`/AA-column matching logic.
- **Missing title opinions are expected, not an error state**, given the client's still-uploading 100+ GB dataset. The system already treats "no PDF" as a WARNING, never a hard failure, and this is validated as the intended posture, not a workaround.

---

## 6. Known gaps — things the system does NOT do yet

These are real gaps, not disagreements about scope. Ranked roughly by how much they affect deliverable trustworthiness:

1. **No cross-reference against the Declaration of Pooled Unit / Designation of Unit.** The team process explicitly requires opening the DPU/DOU, going to Exhibit A, and confirming the lease list matches what the spreadsheet says belongs to the unit (Trevor Dahl, 00:14:37 and 00:38:18). The system currently trusts the XREF's own AA-column unit tagging with no independent cross-check against the DPU document itself. This is a real verification step a human is expected to perform that nothing in the pipeline attempts, even partially.

2. **No filtering of "filed/recorded" vs. "internal, non-recorded" documents.** Trevor is explicit (00:21:43) that most files in a lease folder are irrelevant internal paperwork. The current `apply_supplemental_scope_filter` only checks (a) date vs. controlling cert date and (b) whether a party fuzzy-matches the Seller — it has no notion of "is this instrument actually of record" (recording info present, instrument number present, etc.). A non-recorded internal memo that happens to post-date the cert date and mention EOG would currently pass the filter and land in the Runsheet.

3. **No "lease files folder" bundling in the deliverable.** Trevor's description of what gets submitted includes not just the report but a companion folder with a subfolder per lease containing the underlying source documents downloaded from Drive (00:19:14). The pipeline currently produces only the filled DDR — it does not package or reference the source PDFs it consumed as a deliverable artifact.

4. **`tract_gross_acres` extraction is best-effort, not validated.** The LLM extracts a bare acreage number from the tract legal description; there is no cross-check against a plat, survey, or the Well List's own acreage field (if one exists — needs checking). This is explicitly flagged to the landman in Section Notes, but the flag is the only safeguard; nothing stops a garbled OCR read (e.g., "19.2" instead of "119.2") from silently propagating into the WI/NRI denominator.

5. **Ownership basis selection can silently pick an older opinion over a newer one if the newer one's ownership tables are unparseable.** This happened in one BOWEN A UNIT run (the Second Supplement's Seller WI was stated as a prose formula `"62.5% x 7/8 less (62.5% x 50% x 5%) less (62.5% x 4.5%)"` that the fraction parser could not fully resolve, so the system fell back to the Original 2008 opinion). This is documented behavior (falls back rather than erroring), but it means the "controlling" opinion used for aggregation is not always the one with the latest certification date — it is the latest one the parser could make sense of. This should be surfaced as its own explicit flag (currently folded into the generic "ownership basis" Section Note, which does not call out that a *more recent* opinion existed but was skipped for parseability reasons).

6. **Percent-with-deduction formulas are not parsed.** `parse_fraction_text` now handles bare percentages ("62.5%") but not compound expressions with "less (...)" subtraction clauses, which appear in at least one real title opinion in this dataset. These rows are dropped from aggregation rather than computed, silently reducing the row count feeding into WI/NRI totals.

7. **No automated linkage between Lease Review and the DPU/Well List's declared acreage per lease.** Lease Review rows are built by fuzzy-matching lessor names between the XREF and the parsed TO lease blocks (`SELLER_PARTY_MATCH_THRESHOLD = 80`); there is no independent numeric check that the sum of matched lease acreages equals the unit's total.

8. **Multi-unit project throughput has not been tested end-to-end.** Every real run in this assessment was single-unit (BOWEN A UNIT only). The Project Log has ~300 assignable units; the "process all units" path (no `unit_name_filter`) exists in code but has not been run against real client data — only against a synthetic/smoke-test path in earlier development.

9. **Reconciliation tolerance (`DD_RECONCILIATION_TOLERANCE = 0.0005`) is a code constant, not confirmed against team-specified tolerance.** No source in the transcripts or written instructions specifies an acceptable WI/NRI delta; this value was chosen internally and has not been validated against what PLM/EOG actually consider a "PASS."

10. **Agreements / Unit and Pooling Agreements tabs pull only `record_type`, `file_number`, `lessor`/`lessee` from the XREF's contract rows.** `ReferenceContractRef` does not carry `recording_info`, `effective_date`, `unit_description`, or `formations` — so the "Unit and Pooling Agreements" card in the DDR is structurally correct (fixed this cycle) but substantively incomplete: several of the template's own labeled fields (Recording Information, Effective Date, Unit Description, Formations) have no data source wired to them at all yet.

11. **No handling of the "not all Drive folders are uploaded yet" state as a first-class pipeline signal.** The system treats a missing TO PDF as "PDF not yet available for review" per-opinion, which is correct, but there is no unit-level summary distinguishing "this unit's data is simply incomplete because upload is still in progress" from "this unit's title genuinely could not be resolved." Both currently surface as the same kind of WARNING/flag text.

12. **MOR and DD are architecturally separate pipelines with duplicated concepts** (both have their own classification/QA-adjacent logic; MOR's `classify_documents`/`run_qa` are reused inside DD for the supplemental-document path, but DD's title-opinion-specific extraction, aggregation, and reconciliation are a parallel system with no shared abstraction). This is a maintainability observation, not a correctness bug — flagging for awareness since the two pipelines could drift.

---

## 7. Deliverable checklist — DDR template tab-by-tab status

| Tab | Populated? | Data source | Known limitation |
|---|---|---|---|
| Summary | Yes | Manifest + review-flag builder | Landman name / date submitted always blank (no source for these) |
| Ownership Report | Yes | TO aggregation + XREF leases | Depends entirely on `select_ownership_basis` picking the right TO (see gap #5) |
| Ownership - Wells | Yes | Well List + reconciliation result | Reconciliation numbers repeat per well row (not per-well WI/NRI, unit-level only) |
| Lease Review | Yes | XREF leases + fuzzy-matched TO lease blocks | Rows with no TO match get only lessor/lessee/lease_no, rest blank |
| Agreements | Partial | XREF contract rows (JOA/Farmout/Assignment) | Card shows operator/counterparty only; no effective date, depth limits, non-consent terms — template has fields for these with no data source |
| Unit and Pooling Agreements | Partial | XREF unit-agreement rows | Card layout fixed this cycle; recording info / effective date / unit description / formations fields structurally present but unpopulated (gap #10) |
| Runsheet | Yes (when supplemental docs supplied) | MOR-style classify/QA pipeline reused for the post-cert-date document list | Only as complete as the supplemental instrument PDFs actually uploaded — the BOWEN A UNIT test run had 0 supplemental instruments uploaded, so Runsheet is currently just the header/note, no rows |
| PLM Title Review | Yes | TO extractions | "No PDF" / "Parse error" opinions get placeholder text, correctly distinguished from successfully parsed ones |
| Disclaimer | Static | Template boilerplate | Unmodified, as intended |
| DD_Audit_Trail | Yes | `DDRWriteContext` recorder | Comprehensive; every written cell has a provenance row |

**Bottom line on the deliverable:** for a unit with all 3 reference workbooks + all relevant TO PDFs + supplemental instrument PDFs supplied, the DDR is now substantively filled with real, traceable data and explicit manual-review flags — a major change from the all-blank template the system produced before this session's fixes. The two tabs most likely to disappoint a reviewer expecting completeness are **Agreements** and **Unit and Pooling Agreements** (structurally correct but missing several template-promised fields) and **Runsheet** (entirely dependent on whether supplemental instrument PDFs were actually uploaded for that unit — this run had none).

---

## 8. Test coverage

127 tests, all passing, spanning:
- `test_dd_manifest_builder.py` — XREF/Project Log/Well List parsing, unit matching, confirm_coverage logic
- `test_dd_title_opinion_parser.py` — LLM extraction schema, retry/cache, max_tokens truncation handling
- `test_dd_unit_aggregation.py` — Fraction arithmetic, fraction-text parsing (including new `%` support), reconciliation thresholds
- `test_dd_pipeline_supplemental_scope.py` — scope filter, controlling-date resolution, hard-stop behavior
- `test_dd_ddr_writer.py` — template-filling correctness for every tab, card-block alignment, sample-row clearing
- Remaining MOR test files (`test_classifier.py`, `test_qa.py`, `test_pdf_reader.py`, etc.) unaffected by DD work

No integration test exercises the full `dd_upload_runner.run_dd_upload()` path against real client files with real API calls — everything in §3 was verified via ad hoc scripts run during this session, not committed as an automated regression test. **This is itself a gap**: the BOWEN A UNIT scenario that surfaced 5 real bugs this session (max_tokens truncation, date-parsing failure, tract over-segmentation, card-block misalignment, sample-row leakage) had zero automated coverage before being caught by manual inspection of a real run's output. Recommend building at least one fixture-based integration test using redacted/synthetic versions of the 3 real title opinions to lock in the current de-dup + basis-selection behavior.

---

## 9. Recommendation for the reviewing Claude / human

Priority order if continuing this work:
1. Close gap #2 (recorded-vs-internal document filtering) — this is the single biggest risk of a wrong Runsheet entry making it into a client deliverable.
2. Close gap #1 (DPU/DOU cross-reference) — currently zero automated or semi-automated support for a step the team explicitly calls mandatory.
3. Add the integration test called out in §8 before making further changes to `dd_pipeline.py` or `title_opinion_parser.py` — the BOWEN A UNIT case is a good fixture and currently has no regression protection.
4. Decide and document an explicit answer to gap #9 (reconciliation tolerance) with input from Trevor Dahl/PLM leadership rather than leaving it as an internal constant.
5. Extend `ReferenceContractRef` (gap #10) if Agreements/Unit-and-Pooling completeness is required for client sign-off, or explicitly scope it out if not.
