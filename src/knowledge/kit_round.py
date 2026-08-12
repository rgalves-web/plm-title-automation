"""The kit round, as a declared entrypoint — not a script in /tmp.

A round that lives outside the repo is a round whose writes nobody declared:
the /tmp script this replaces wrote into `data/units/` from outside any scope,
which is exactly how the repo grew the strays the 2026-08-12 audit catalogued.

This runner opens a `write_scope` over the replay namespace before anything is
written and emits `write_manifest.json` when it ends — including on failure.
Sources are read in place: the corpus from the original zips (read-only), the
round state from `_work/` (disposable, regenerable).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from src.knowledge.clean_output import check_checklist
from src.knowledge.corpus_reader import CorpusIndex
from src.knowledge.josh_b_round import CASE, FILES_DIR, UNIT, WORK, run
from src.knowledge.kit_builder import (CHECKLIST_ROW_TO_FOLDER, BuildResult,
                                       build_tree, fill_checklist, is_shippable,
                                       write_ddr, write_manifest)
from src.knowledge.runsheet import Basis
from src.knowledge.runsheet import build as build_runsheet
from src.knowledge.write_roots import write_scope

PROJECT = Path("C:/Users/Renato/PURPLE LAND MGMT/BKV122TX - Project Emirates")
TEMPLATE = PROJECT / "DDR - Template (PLM).xlsx"
CHECK_TEMPLATE = (PROJECT / "JOSH B UNIT" / "1. Landman Submitted"
                  / "Phase I - Checklist.xlsx")
KIT = CASE / "KIT"

# find_cert_date returns BLOCKING for all three opinions: none prints a
# certification sentence. The run uses the earliest candidate — over-including,
# the safe direction for a chain of title — and declares the basis in the tab.
RUNSHEET_BASIS = Basis(cert_date=date(2010, 4, 9), confirmed=False, statement=(
    "PROVISIONAL BASIS — no opinion in the file prints a certification "
    "sentence. Run from April 9, 2010, the earliest candidate found (the "
    "runsheet through-date recited under DOCUMENTS EXAMINED in the A-669 "
    "50-acre opinion, p.8; the A-319 opinion's candidate is May 21, 2010, "
    "p.36). The certification dates are an open blocking item: confirm them "
    "before this run is relied upon. Unit Tract 1 has no opinion of record, "
    "so no run has been made for it."))


@dataclass
class KitRound:
    result: BuildResult
    brief_problems: int
    checklist_tally: dict[str, int]
    manifest_path: Path
    write_manifest_path: Path


def _classifications() -> list[dict[str, Any]]:
    cls = json.loads((WORK / "classifications.json").read_text(encoding="utf-8"))
    loose = WORK / "classifications_loose.json"
    if loose.exists():
        cls += json.loads(loose.read_text(encoding="utf-8"))
    return cls



def _tab_payloads() -> tuple[dict, list, list]:
    """Everything the PR-10 tabs need, plus the brief items owning the blanks."""
    import re

    import yaml as _yaml

    from src.knowledge import ddr_tabs
    from src.knowledge.fetch_brief import (ACTION_FETCH, ACTION_REQUEST,
                                           ACTION_VERDICT, BriefItem)
    from src.knowledge.josh_b_round import live_requirements
    from src.knowledge.unit_ownership import load_schedules

    engagement = _yaml.safe_load(
        Path("knowledge/project/engagement.yaml").read_text(encoding="utf-8"))
    unit_authority = "recorded unit designation Vol. 611, Pg. 526 p.1"

    # Exhibit "C" tract schedule, parsed from the round's own DPU read.
    import json as _json
    p6 = next(x["text"] for x in _json.loads(
        (WORK / "_josh_b_dpu_vision.json").read_text(encoding="utf-8"))
        if x["page"] == 6)
    exhibit_c = {}
    block = re.search(r"MINERAL OWNER\s+ACREAGE(.*?)TOTAL ACREAGE", p6, re.S)
    for m in re.finditer(r"^\s*(\d)\s{2,}(.+?)\s{2,}([\d.]+)\s*$",
                         block.group(1), re.M):
        exhibit_c[m.group(1)] = {"owner": m.group(2).strip(),
                                 "acres": m.group(3)}

    schedules = load_schedules(WORK)

    # lease -> (opinion tag, the opinion's own lease number, its tract). The
    # join is the RECORDING: the opinion's lease summary and Exhibit "A" name
    # the same instrument, and only the volume/page tells two leases of one
    # lessor apart.
    from src.knowledge.term_source import norm_recording
    from src.knowledge.to_schedule import merge_schedules, parse_schedule
    to_schedule_by_lease: dict[str, dict[str, Any]] = {}
    exhibit_a = _json.loads(
        (WORK / "_josh_b_exhibitA.json").read_text(encoding="utf-8"))["leases"]
    rec_to_lease = {norm_recording(v.get("recording")): lease
                    for lease, v in exhibit_a.items()
                    if norm_recording(v.get("recording"))}
    for tag, filename in (("a319", "_to_a319_read.json"),):
        path = WORK / filename
        if not path.exists():
            continue
        blocks = _json.loads(path.read_text(encoding="utf-8"))["schedule"]
        clause = WORK / filename.replace("_read.json", "_clauses.json")
        entries = (merge_schedules(blocks,
                                   _json.loads(clause.read_text(encoding="utf-8")))
                   if clause.exists() else parse_schedule(blocks))
        for e in entries:
            lease = rec_to_lease.get(norm_recording(e.get("recording_book_page")))
            if not lease:
                continue
            land = str((e.get("terms") or {}).get("legal_description") or "")
            tract = ("Tract 1" if "Tract 1" in land
                     else "Tract 2" if "Tract 2" in land else "")
            to_schedule_by_lease[lease] = {"tag": tag,
                                          "lease_no": e["lease_no"],
                                          "tract": tract}
    # Opinion-tract -> unit-tract. Tract 1 is DOCUMENTED; the other three are
    # INFERENCES from Exhibit "C" owners/acreage, owned by item TRACT-MAP.
    t1_evidence = ("DPU Exhibit B p.5 begins within Tract 1 of Vol. 217 Pg. "
                   "491, the land this opinion covers; Exhibit C Tract 1 "
                   "owner STEWART matches the opinion Stewart owners")
    inferred = ("INFERRED from Exhibit C owner/acreage - requires human "
                "verdict (brief item TRACT-MAP)")
    tract_map = {
        "a669_50": {"": {"unit_tract": "1", "evidence": t1_evidence},
                    "All Tracts": {"unit_tract": "1", "evidence": t1_evidence}},
        "a669_155": {"All Tracts": {"unit_tract": "2", "evidence": inferred},
                     "": {"unit_tract": "2", "evidence": inferred}},
        "a319": {"Tract 1": {"unit_tract": "4", "evidence": inferred},
                 "Tract 2": {"unit_tract": "3", "evidence": inferred}},
    }

    # RRC CSVs, in the corpus, read in place.
    wb_csv = (FILES_DIR / "WellboreQueryResults_ReportCsv (1).csv").read_text(
        encoding="utf-8", errors="replace")
    api = re.search(r"API No\.: ([0-9-]+)", wb_csv).group(1)
    row = re.search(r'^(\d+),\d+,(\d+),"([^"]+)",(\w+),"([^"]+)","([^"]+)",'
                    r"(\w+),\w+,(\d+)", wb_csv, re.M)
    wellbore = {
        "api": api,
        "lease_name": f"{row.group(3)} #{row.group(4)}",
        "field": row.group(5), "operator": row.group(6),
        "api_depth": row.group(8),
        "cite": "WellboreQueryResults_ReportCsv (1).csv (RRC wellbore query, "
                "in FILES/)",
        "well_type": "Gas",
        "type_cite": "SpecificLeaseQuery_prodAndTotalDisp_ReportCsv.csv "
                     "(Well Type: Gas)",
    }
    prod_csv = (FILES_DIR / "SpecificLeaseQuery_prodAndTotalDisp_ReportCsv.csv"
                ).read_text(encoding="utf-8", errors="replace")
    gaps_text, gaps_cite = ddr_tabs.production_gaps(prod_csv)

    gaps = live_requirements()
    curative_bits = []
    for g in gaps:
        piece = g.subject
        if g.cause_no:
            piece += f" ({g.cause_no})"
        if g.county and g.county.lower() != "montague":
            piece += f" - of record in {g.county} County, NOT Montague"
        curative_bits.append(piece)
    curative_text = ("OPEN REQUIREMENTS of the controlling opinions: "
                     + "; ".join(curative_bits))
    curative_cite = ("COMMENTS AND REQUIREMENTS of the A-319 and A-669 "
                     "opinions, read requirement by requirement (pages in "
                     "fetch_brief.yaml, items CURATIVE-*)")

    landman_cfg = {}
    cfg_path = Path("config.yaml")
    if cfg_path.exists():
        landman_cfg = _yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    landman = str(landman_cfg.get("landman_name") or "")
    landman_cite = ("declared operator datum: config.yaml landman_name"
                    if landman else "")

    payload = {
        "engagement": engagement, "unit_authority": unit_authority,
        "exhibit_c": exhibit_c, "schedules": schedules,
        "tract_map": tract_map, "wellbore": wellbore,
        "gaps_text": gaps_text, "gaps_cite": gaps_cite,
        "curative_text": curative_text, "curative_cite": curative_cite,
        "landman": landman, "landman_cite": landman_cite,
        "to_schedule_by_lease": to_schedule_by_lease,
        "legal": ("220.00 acres, more or less, in the W. Scarbrough Survey, "
                  "A-669, and the Hill County School Land Survey, A-319, "
                  "Montague County, Texas"),
    }

    extra_items = [
        BriefItem(
            id="AGREEMENTS-REQUEST",
            what="JOAs / operating agreements for JOSH B UNIT - no instrument "
                 "in the corpus proves one, so the Agreements tab stays blank",
            where=["Seller (EOG Resources, Inc.), via PLM"],
            how="Request by e-mail: any JOA, farmout or operating agreement "
                "covering the Josh B Unit lands. No cost. No agreement card "
                "is written from a recital.",
            looks_like="An executed operating agreement naming the unit lands.",
            unlocks=["Agreements!JOA"],
            already_searched=["all 214 corpus documents classified; none is "
                              "an operating agreement for this unit"],
            blocking=False, action=ACTION_REQUEST,
            source="third_party_request", effort="one e-mail",
            origin="Agreements tab blank with reason"),
        BriefItem(
            id="RRC-FETCH",
            what=f"RRC well files for API {api}: W-1, P-12, well plat, "
                 "completion report - spud/completion/status cells stay blank "
                 "until these arrive",
            where=["RRC: webapps.rrc.texas.gov -> ewaMain.do -> Drilling "
                   "Permit (W-1) Query -> API",
                   "gis.rrc.texas.gov for the plat"],
            how=f"ewaMain.do -> W-1 Query -> API {api.replace('-', '')}; "
                "completion query by the same API. If the site answers "
                "'application error', record the attempt and keep the item "
                "open - never convert it to unfindable.",
            looks_like="RRC forms naming the well JOSH B UNIT #1H.",
            unlocks=["Ownership - Wells!spud_date",
                     "Ownership - Wells!completion_date",
                     "Ownership - Wells!well_status",
                     "Ownership - Wells!drill_type"],
            already_searched=["corpus holds only the wellbore and production "
                              "query CSVs; no W-1/P-12/plat"],
            blocking=False, action=ACTION_FETCH, source="rrc",
            effort="one 30-minute sitting",
            origin="Ownership - Wells blanks"),
        BriefItem(
            id="TRACT-MAP",
            what="Confirm the opinion-tract to unit-tract mapping: A-669 "
                 "155ac -> Unit Tract 2; A-319 Tract 1 (211 ac) -> Unit Tract "
                 "4; A-319 Tract 2 (107.30 ac) -> Unit Tract 3",
            where=["DPU Exhibit C tract schedule (held)",
                   "the three opinions (held)"],
            how="Rule on the inference: Exhibit C owners (D. HARRISON ET AL / "
                "M.K. SLAUGHTER / DR. S. SCHMIDT) against the opinions' owner "
                "lists. Unit Tract 1 is documented; the other three are "
                "inferred.",
            looks_like="A confirmation, not a document.",
            unlocks=["Ownership - Worksheet!unit_tract_mapping"],
            already_searched=["Exhibit C read; opinion ownership schedules "
                              "read"],
            blocking=False, action=ACTION_VERDICT, source="drive_plm",
            effort="minutes",
            origin="unit-tract column of the Worksheet rows"),
    ]
    extra_blanks = ["Agreements!JOA",
                    "Ownership - Wells!spud_date",
                    "Ownership - Wells!completion_date",
                    "Ownership - Wells!well_status",
                    "Ownership - Wells!drill_type",
                    "Ownership - Worksheet!unit_tract_mapping"]

    if not landman:
        extra_items.append(BriefItem(
            id="LANDMAN",
            what="Landman name for PLM Title Review - operator datum not "
                 "declared in config.yaml (landman_name)",
            where=["config.yaml (add landman_name)"],
            how="One line in config.yaml: landman_name: <name as it should "
                "appear in the deliverable>.",
            looks_like="A declaration, not a document.",
            unlocks=["PLM Title Review!landman"],
            already_searched=["config.yaml has no landman_name key"],
            blocking=False, action=ACTION_VERDICT, source="drive_plm",
            effort="one line",
            origin="PLM Title Review blank with reason"))
        extra_blanks.append("PLM Title Review!landman")

    return payload, extra_items, extra_blanks


def build_kit(submitted: str) -> KitRound:
    """The whole round, inside one declared write scope."""
    corpus = CorpusIndex(FILES_DIR)
    payload, extra_items, extra_blanks = _tab_payloads()

    with write_scope(CASE, label=f"kit round {UNIT} {submitted}") as scope:
        r = run(submitted, extra_items=extra_items, extra_blanks=extra_blanks)
        disps = [d.to_dict() for d in r["dispositions"]]
        cls = _classifications()

        # --- S6: runsheet first — Title Documents IS the runsheet ----------
        of_record_by_file = {}
        rec = {d["lease"]: d.get("recording") for d in disps}
        for c in cls:
            of_record_by_file[str(c.get("file", ""))] = bool(
                rec.get(str(c.get("lease"))))
        outside = {d["lease"] for d in disps
                   if d["status"] == "outside_perimeter"}
        outside_files = {str(c.get("file", "")) for c in cls
                         if str(c.get("lease")) in outside}
        entries, dropped = build_runsheet(
            cls, cert_date=RUNSHEET_BASIS.cert_date, basis=RUNSHEET_BASIS,
            of_record_by_file=of_record_by_file, outside_files=outside_files)

        # Summary defects text, derived from THIS round's dispositions.
        from src.knowledge import ddr_tabs
        missing_leases = [d["lease"] for d in disps
                          if d["status"] in ("terms_sourced_instrument_missing",
                                             "memo_only")]
        defects_text = (
            f"MISSING LEASES - {len(missing_leases)} leases named in Exhibit "
            "A lack the recorded instrument in the Seller's files: "
            + ", ".join(missing_leases)
            + ". Terms of record are filled from the opinions/Exhibit A and "
              "cited per cell in DD_Audit_Trail; the instruments are "
              "requested from the Seller (brief items SELLER-DELIVERY / "
              "MISSING-LEASE / LEASE-FETCH).")
        defects_cite = ("derived from the round's dispositions; per-lease "
                        "citations in the Lease Review rows of DD_Audit_Trail")

        extra_writers = [
            lambda wb, w: ddr_tabs.write_summary(
                wb, w, engagement=payload["engagement"],
                unit_authority=payload["unit_authority"],
                defects_text=defects_text, defects_cite=defects_cite,
                curative_text=payload["curative_text"],
                curative_cite=payload["curative_cite"]),
            lambda wb, w: ddr_tabs.write_worksheet(
                wb, w, schedules=payload["schedules"],
                tract_map=payload["tract_map"],
                exhibit_c=payload["exhibit_c"], dispositions=disps,
                to_schedule_by_lease=payload["to_schedule_by_lease"],
                county="Montague"),
            lambda wb, w: ddr_tabs.write_wells(
                wb, w, wellbore=payload["wellbore"],
                gaps_text=payload["gaps_text"], gaps_cite=payload["gaps_cite"],
                unit_size="220.00",
                unit_cite="recorded unit designation Vol. 611, Pg. 526 p.1 "
                          "(220.0 acres, Barnett Shale only)"),
            lambda wb, w: ddr_tabs.write_plm_title_review(
                wb, w, cert_basis=RUNSHEET_BASIS.statement,
                legal_description=payload["legal"],
                legal_cite="DPU Exhibit B p.5 (metes and bounds opening)",
                scope_text="Supplemental title review of the Seller's "
                           "leasehold from the opinions' certification dates "
                           "to present; certification dates provisional (see "
                           "Title Certification Dates).",
                scope_cite="BPM - Due Diligence (Leasehold).pdf, Title Work",
                landman=payload["landman"],
                landman_cite=payload["landman_cite"],
                submitted=submitted),
        ]
        ddr, writes = write_ddr(TEMPLATE, KIT / f"DDR - {UNIT.title()}.xlsx",
                                disps, unit=UNIT, submitted=submitted,
                                runsheet_entries=entries,
                                runsheet_basis=RUNSHEET_BASIS,
                                extra_writers=extra_writers)
        result = BuildResult(ddr_path=ddr, cells=writes,
                             problems=list(r["problems"]))

        # --- S8: the carbon-copy tree, sources read from the zips ----------
        by_cat: dict[str, list[Any]] = {}
        for c in cls:
            if not is_shippable(Path(str(c["file"])), c):
                continue
            if not (Path(str(c["file"])).exists() or corpus.exists(c["file"])):
                continue
            cat = c.get("classified_as")
            dest = {"title_opinion": "Title Opinions",
                    "dpu": "Unit Designations",
                    "deed_release_lien": "Title Documents",
                    "assignment": "Title Documents",
                    "probate_heirship": "Title Documents",
                    "well_file": "Well Files",
                    "ownership_report": "Seller Files"}.get(str(cat))
            if dest:
                by_cat.setdefault(dest, []).append(c["file"])
        dpu = (PROJECT / "JOSH B UNIT" / "1. Landman Submitted"
               / "Unit Designations" / "611.526.pdf")
        if dpu.exists():
            by_cat.setdefault("Unit Designations", []).append(dpu)
        extras = {k: sorted(set(map(str, v)), key=lambda x: Path(x).name)
                  for k, v in by_cat.items()}

        placed, missing = build_tree(KIT, unit_title=UNIT.title(),
                                     dispositions=disps, classifications=cls,
                                     ddr_path=ddr, extras=extras, corpus=corpus)
        result.tree, result.missing = placed, missing

        # --- Phase I - Checklist: Yes/No DERIVED from the artefact bytes ----
        # (PR-9 item 5). "Populated" is a fact about the file, not a claim the
        # runner makes about itself.
        from src.knowledge.template_structure import (
            check_checklist_vs_artifact, tabs_populated)
        tabs_done = tabs_populated(ddr)
        notes: dict[int, str] = {}
        derived: dict[int, set[str]] = {}
        for row, folder in [(2, "Leases"), (11, "Seller Files"),
                            (12, "Title Documents"), (13, "Title Opinions"),
                            (14, "Unit Designations"), (15, "Well Files")]:
            gaps = [m for m in missing if m["folder"] == folder]
            if gaps:
                held, pending = len(placed.get(folder, [])), len(gaps)
                notes[row] = (f"{held} placed; {pending} declared pending — "
                              f"see SUBMISSION_MANIFEST.txt")
                derived[row] = {str(held), str(pending)}
        for row, tab in [(4, "Ownership - Worksheet"), (5, "Ownership - Wells"),
                         (7, "Agreements"), (10, "PLM Title Review")]:
            if not tabs_done.get(tab):
                notes[row] = "not populated this round — outside the scope executed"
        checklist, tally = fill_checklist(
            CHECK_TEMPLATE, KIT / "1. Landman Submitted" / "Phase I - Checklist.xlsx",
            placed=placed, tabs_done=tabs_done, notes=notes)
        chk = check_checklist(checklist, placed=placed,
                              row_to_folder=CHECKLIST_ROW_TO_FOLDER,
                              derived_numbers=derived)
        if chk.failed:
            raise AssertionError(f"checklist gate FAILED: {chk.summary()}")
        from src.knowledge.kit_builder import CHECKLIST_ROW_TO_TAB
        vs = check_checklist_vs_artifact(checklist, ddr, CHECKLIST_ROW_TO_TAB)
        if vs.failed:
            raise AssertionError(
                f"checklist contradicts the artefact: {vs.summary()}")

        manifest = write_manifest(KIT, placed, missing, result)
        (KIT / "build_result.json").write_text(json.dumps(
            {"cells": [c.to_dict() for c in writes], "tree": placed,
             "missing": missing, "evidenced": result.evidenced,
             "declared": result.declared, "orphan": result.orphan,
             "converged": result.converged()},
            indent=1, ensure_ascii=False), encoding="utf-8")
        scope.check(KIT / "build_result.json")

    return KitRound(result=result, brief_problems=len(r["problems"]),
                    checklist_tally=tally, manifest_path=manifest,
                    write_manifest_path=CASE / "write_manifest.json")
