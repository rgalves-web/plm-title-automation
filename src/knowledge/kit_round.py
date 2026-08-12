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


def build_kit(submitted: str) -> KitRound:
    """The whole round, inside one declared write scope."""
    corpus = CorpusIndex(FILES_DIR)

    with write_scope(CASE, label=f"kit round {UNIT} {submitted}") as scope:
        r = run(submitted)
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

        ddr, writes = write_ddr(TEMPLATE, KIT / f"DDR - {UNIT.title()}.xlsx",
                                disps, unit=UNIT, submitted=submitted,
                                runsheet_entries=entries,
                                runsheet_basis=RUNSHEET_BASIS)
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
