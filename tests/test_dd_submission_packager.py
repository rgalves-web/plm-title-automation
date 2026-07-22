"""PLM Submission Packager: assemble the required Drive folder for a unit.

Every placed file must trace to a real document; anything expected-but-absent
goes to MISSING so the gap is visible, never hidden.
"""
from __future__ import annotations

from pathlib import Path

from src.dd.submission_packager import (
    MANIFEST_NAME,
    SUBFOLDERS,
    build_plan_from_unit_folder,
    build_submission_plan,
    classify_unit_files,
    expand_archives,
    package_unit_submission,
    parse_vol_page,
    render_manifest,
    select_used_title_opinions,
    stage_submission,
    title_case_unit_name,
)


def _index(paths):
    from src.dd.submission_packager import _norm
    return {_norm(Path(p).stem): Path(p) for p in paths}


def _plan(**kw):
    base = dict(unit_name="MAXWELL A UNIT", ddr_path=None, consumed_title_opinions=[],
                dpu_files=[], lease_files=[], runsheet_rows=[], sellers_files=[],
                well_files=[], file_index={})
    base.update(kw)
    return build_submission_plan(**base)


# --- unit-name title casing ------------------------------------------------

def test_unit_name_title_cased_keeps_the_A_and_Unit():
    assert title_case_unit_name("MAXWELL A UNIT") == "Maxwell A Unit"
    assert title_case_unit_name("ALAMO B UNIT") == "Alamo B Unit"
    assert title_case_unit_name("OLD BRASS AND NEEDLE UNIT") == "Old Brass and Needle Unit"


def test_unit_name_not_naive_str_title():
    # str.title() would give "Maxwell A Unit" here too, but botches possessives
    # and single letters elsewhere; ours keeps "A" upper, not "a".
    assert title_case_unit_name("MAXWELL A UNIT").split()[1] == "A"


# --- dedupe of repeated title opinions -------------------------------------

def test_repeated_title_opinions_are_deduped_to_one_copy(tmp_path):
    cox = tmp_path / "T-O SUPP LYNN W COX ET AL A-122.PDF"
    cox.write_bytes(b"x")
    idx = _index([cox])
    plan = _plan(consumed_title_opinions=[
        "T-O SUPP LYNN W COX ET AL A-122",
        "T-O SUPP LYNN W COX ET AL A-122 pp.5-6 (MINERALS)",   # same opinion, page cite
        "T-O SUPP LYNN W COX ET AL A-122",                     # exact repeat
    ], file_index=idx)
    placed = plan.for_subfolder(SUBFOLDERS[1])
    assert len(placed) == 1
    assert any("deduped" in d for d in plan.decisions)


def test_same_opinion_under_two_filenames_is_deduped_by_chain(tmp_path):
    # The real Maxwell drop had the Kramer original twice under different names.
    a = tmp_path / "T-O ORIG KRAMER MINERAL TRUST EL AL A-122 BLK 7 22.333AC.PDF"
    b = tmp_path / "T-O ORIG KRAMER MINERAL TRUST ET AL - A-122 LEAGUE 12 - 22.3333AC.PDF"
    a.write_bytes(b"1"); b.write_bytes(b"2")
    plan = _plan(consumed_title_opinions=[a.stem, b.stem], file_index=_index([a, b]))
    assert len(plan.for_subfolder(SUBFOLDERS[1])) == 1
    assert any("same opinion" in d and "KRAMER" in d for d in plan.decisions)


def test_original_and_supplement_are_both_kept(tmp_path):
    orig = tmp_path / "T-O ORIG LYNN W. COX ET AL A-122 BLK 10 AND 11 140.9963 REVISED.PDF"
    supp = tmp_path / "T-O SUPP LYNN W COX ET AL A-122 BLK 10 AND 11 140.9963AC.PDF"
    orig.write_bytes(b"1"); supp.write_bytes(b"2")
    plan = _plan(consumed_title_opinions=[orig.stem, supp.stem], file_index=_index([orig, supp]))
    assert len(plan.for_subfolder(SUBFOLDERS[1])) == 2   # ORIG and SUPP are distinct docs


def test_a_cited_TO_with_no_file_goes_to_missing(tmp_path):
    plan = _plan(consumed_title_opinions=["T-O ORIG NONEXISTENT A-999"], file_index={})
    assert not plan.for_subfolder(SUBFOLDERS[1])
    assert any("NONEXISTENT" in m.what for m in plan.missing)


# --- volume.page renaming --------------------------------------------------

def test_vol_page_parsed_from_a_runsheet_row():
    assert parse_vol_page("Doc 95850, OPR Vol. 492, Pg. 510") == ("492", "510")
    assert parse_vol_page("Book 407 Page 123") == ("407", "123")
    assert parse_vol_page("no volume here") is None


def test_title_document_is_renamed_volume_dot_page(tmp_path):
    src = tmp_path / "SOME RECORDED LEASE Vol 407 Pg 123.pdf"
    src.write_bytes(b"x")
    idx = _index([src])
    plan = _plan(runsheet_rows=[{"instrument": "OGML Brashear to EOG",
                                 "source_ref": "Doc 1, OPR Vol. 407, Pg. 123"}],
                 file_index=idx)
    placed = plan.for_subfolder(SUBFOLDERS[4])
    assert len(placed) == 1
    assert placed[0].dest_name == "407.123.pdf"
    assert "renamed from" in placed[0].note


def test_runsheet_instrument_with_no_file_goes_to_missing():
    plan = _plan(runsheet_rows=[{"instrument": "OGML Ratliff to EOG",
                                 "source_ref": "Vol. 492, Pg. 519"}],
                 file_index={})
    assert not plan.for_subfolder(SUBFOLDERS[4])
    assert any("492" in m.what and "519" in m.what for m in plan.missing)


def test_runsheet_row_with_no_parseable_volpage_goes_to_missing():
    plan = _plan(runsheet_rows=[{"instrument": "Affidavit of heirship", "source_ref": "unrecorded"}])
    assert any("no volume/page" in m.reason for m in plan.missing)


# --- Seller's Files: conservative inclusion ---------------------------------

def test_division_order_is_excluded_from_sellers_files(tmp_path):
    do = tmp_path / "DIVISION ORDER - Maxwell 1H.pdf"; do.write_bytes(b"x")
    farmout = tmp_path / "FARMOUT AGREEMENT - Encana to EOG.pdf"; farmout.write_bytes(b"x")
    plan = _plan(sellers_files=[do, farmout])
    placed = {p.source.name for p in plan.for_subfolder(SUBFOLDERS[5])}
    assert "FARMOUT AGREEMENT - Encana to EOG.pdf" in placed
    assert "DIVISION ORDER - Maxwell 1H.pdf" not in placed
    assert any("division order" in d.lower() and "excluded" in d.lower() for d in plan.decisions)


def test_bonus_receipt_and_lar_are_excluded(tmp_path):
    for name in ("BONUS RECEIPT.pdf", "LEASE ACQUISITION REPORT.pdf", "LEASE SUMMARY.pdf"):
        (tmp_path / name).write_bytes(b"x")
    plan = _plan(sellers_files=list(tmp_path.glob("*.pdf")))
    assert plan.for_subfolder(SUBFOLDERS[5]) == []


def test_a_non_source_instrument_is_left_out_conservatively(tmp_path):
    misc = tmp_path / "SOME RANDOM CORRESPONDENCE.pdf"; misc.write_bytes(b"x")
    plan = _plan(sellers_files=[misc])
    assert plan.for_subfolder(SUBFOLDERS[5]) == []
    assert any("not a source-cited" in d for d in plan.decisions)


def test_assignment_is_included_in_sellers_files(tmp_path):
    asmt = tmp_path / "ASSIGNMENT - Joe Bob Smith to EOG.pdf"; asmt.write_bytes(b"x")
    plan = _plan(sellers_files=[asmt])
    assert len(plan.for_subfolder(SUBFOLDERS[5])) == 1


# --- Well Files + manifest + staging ---------------------------------------

def test_absent_well_file_is_noted_missing_not_faked():
    plan = _plan(well_files=[])
    assert plan.for_subfolder(SUBFOLDERS[6]) == []
    assert any("RRC production report" in m.what for m in plan.missing)


def test_manifest_lists_placed_missing_and_decisions(tmp_path):
    do = tmp_path / "DIVISION ORDER.pdf"; do.write_bytes(b"x")
    plan = _plan(sellers_files=[do],
                 runsheet_rows=[{"instrument": "OGML", "source_ref": "Vol 1 Pg 2"}])
    text = render_manifest(plan)
    assert "FILES PLACED" in text and "MISSING" in text and "DECISIONS" in text
    assert "DIVISION ORDER" in text                 # the exclusion decision
    assert "Vol 1 Pg 2" in text or "1" in text      # the missing instrument


def test_stage_creates_the_seven_subfolders_and_copies(tmp_path):
    ddr = tmp_path / "DDR.xlsx"; ddr.write_bytes(b"x")
    cox = tmp_path / "T-O SUPP COX.PDF"; cox.write_bytes(b"y")
    plan = _plan(ddr_path=ddr, consumed_title_opinions=["T-O SUPP COX"],
                 file_index=_index([cox]))
    out = tmp_path / "out"
    root = stage_submission(plan, out)
    assert root.name == "1. Landman Submitted"
    assert root.parent.name == "Maxwell A Unit"
    for sub in SUBFOLDERS:
        assert (root / sub).is_dir()
    assert (root / "1. PLM Report" / "DDR.xlsx").exists()
    assert (root / "2. Title Opinions" / "T-O SUPP COX.PDF").exists()
    assert (root / "SUBMISSION_MANIFEST.txt").exists()


def _write_min_ddr(path, to_note="", runsheet=None):
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active; ws.title = "Ownership Report"
    ws["A1"] = "Owner report"
    if to_note:
        ws["A2"] = to_note
    rs = wb.create_sheet("Runsheet")
    rs["A1"] = "Supplemental Title Runsheet"
    rs["A2"] = "NO."; rs["B2"] = "INSTRUMENT"; rs["C2"] = "INSTRUMENT NUMBER"
    for i, (instr, ref) in enumerate(runsheet or [], start=4):
        rs.cell(i, 1, i - 3); rs.cell(i, 2, instr); rs.cell(i, 3, ref)
    wb.save(path)


def test_package_unit_submission_writes_into_the_unit_folder(tmp_path):
    # A realistic unit folder: FILES/ alongside the DDR, both inside the folder.
    unit = tmp_path / "MAXWELL A UNIT"
    files = unit / "FILES"
    files.mkdir(parents=True)
    (files / "T-O ORIG BRUMBAUGH A-122 212.PDF").write_bytes(b"to")
    (files / "K1400813 (DECL OF POOLED UNIT - MAXWELL UNIT A).zip").write_bytes(b"z")
    _write_min_ddr(unit / "DDR - MAXWELL A UNIT (PLM) (v13).xlsx",
                   to_note="Per T-O ORIG BRUMBAUGH the tract is clear.")

    before = {p.name for p in files.iterdir()}
    root, plan = package_unit_submission(unit, unit_dpu_contract="K1400813")

    # Tree lives inside the unit folder's SUBMISSION dir — not a temp dir.
    submission = unit / "SUBMISSION"
    assert submission in root.parents
    assert str(root).startswith(str(unit))
    assert root.name == "1. Landman Submitted"
    assert root.parent.name == "Maxwell A Unit"
    for sub in SUBFOLDERS:
        assert (root / sub).is_dir()
    # Manifest is written in the SUBMISSION folder itself.
    assert (submission / MANIFEST_NAME).exists()
    assert not (root / MANIFEST_NAME).exists()
    # FILES is left exactly as it was; no scratch dir left behind.
    assert {p.name for p in files.iterdir()} == before
    assert not (submission / ".extract").exists()
    # The Brumbaugh opinion (cited in the note) shipped.
    assert any("BRUMBAUGH" in p.name for p in (root / "2. Title Opinions").iterdir())


def test_package_is_idempotent_no_stale_files_on_rerun(tmp_path):
    unit = tmp_path / "MAXWELL A UNIT"
    files = unit / "FILES"; files.mkdir(parents=True)
    (files / "T-O ORIG BRUMBAUGH A-122 212.PDF").write_bytes(b"to")
    _write_min_ddr(unit / "DDR (v1).xlsx", to_note="BRUMBAUGH cited")
    root1, _ = package_unit_submission(unit)
    # Second run must not accumulate or error.
    root2, plan2 = package_unit_submission(unit)
    assert root1 == root2
    tos = list((root2 / "2. Title Opinions").iterdir())
    assert len(tos) == 1


def test_nothing_is_invented_every_placed_file_exists(tmp_path):
    # A plan built from an empty index places nothing but the DDR; everything
    # else is MISSING, never a fabricated entry.
    plan = _plan(consumed_title_opinions=["T-O GHOST"], dpu_files=[], well_files=[])
    assert plan.placed == []
    assert plan.missing            # ghost TO, DPU, well file all listed


# --- folder classifier: buckets a real FILES folder shape ------------------

def _touch(root, *names):
    for n in names:
        p = root / n
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")


def test_classify_sorts_a_maxwell_shaped_folder(tmp_path):
    _touch(tmp_path,
           "T-O ORIG BRUMBAUGH A-122 212.PDF",
           "K1400813 (DECL OF POOLED UNIT - MAXWELL UNIT A-UNIT AGREEMENT).zip",
           "K1400170 (FARMOUT AGMTASMT - ENCANA TO EOG).zip",
           "K1400049 (ASMT - JOE BOB SMITH-ASSIGNMENT).zip",
           "5 Leases.zip",
           "Copy of Lease to Well and Contract XREF.xlsx",
           "DDR - ALAMO A Unit.xlsx")
    b = classify_unit_files(tmp_path)
    names = lambda k: {p.name for p in b[k]}
    assert any("MAXWELL UNIT A" in n for n in names("dpu"))
    assert any("FARMOUT" in n for n in names("sellers"))
    assert any("ASSIGNMENT" in n for n in names("sellers"))
    assert "5 Leases.zip" in names("leases")
    # XREF workbook and another unit's DDR are noise — never bucketed.
    assert not any("XREF" in n for n in names("leases"))
    assert all("DDR - ALAMO" not in n for k in ("dpu", "leases", "sellers", "wells")
               for n in names(k))
    # A title-opinion PDF sitting in the folder is not auto-placed.
    for k in ("dpu", "leases", "sellers", "wells"):
        assert not any("BRUMBAUGH" in n for n in names(k))


# --- Bug 1: Unit Designation is the unit's OWN DPU + amendments only ---------

def test_foreign_unit_dpu_is_excluded(tmp_path):
    own = tmp_path / "K1400813 (DECL OF POOLED UNIT - MAXWELL UNIT A).zip"
    foreign = tmp_path / "K1400235 (DECL OF POOLED UNIT - WIESE UNIT).zip"
    own.write_bytes(b"x"); foreign.write_bytes(b"y")
    plan = _plan(dpu_files=[own, foreign], unit_dpu_contract="K1400813")
    placed = {p.source.name for p in plan.for_subfolder(SUBFOLDERS[2])}
    assert own.name in placed
    assert foreign.name not in placed
    assert any("WIESE" in d and "excluded" in d.lower() and "another" in d.lower()
               for d in plan.decisions)


def test_own_dpu_amendment_is_included(tmp_path):
    dpu = tmp_path / "K1400813 (DECL OF POOLED UNIT - MAXWELL UNIT A).zip"
    amend = tmp_path / "AMENDMENT TO DECL OF POOLED UNIT - MAXWELL UNIT A Vol 574 Pg 830.pdf"
    dpu.write_bytes(b"x"); amend.write_bytes(b"y")
    plan = _plan(dpu_files=[dpu, amend], unit_dpu_contract="K1400813")
    placed = {p.source.name for p in plan.for_subfolder(SUBFOLDERS[2])}
    assert dpu.name in placed and amend.name in placed          # amendment kept
    amend_placed = next(p for p in plan.for_subfolder(SUBFOLDERS[2])
                        if p.source.name == amend.name)
    assert "amendment" in amend_placed.note.lower()


def test_folder_dpu_expands_own_archive_and_drops_foreign_and_cruft(tmp_path):
    import zipfile
    own = tmp_path / "K1400813 (DECL OF POOLED UNIT - MAXWELL UNIT A).zip"
    with zipfile.ZipFile(own, "w") as zf:
        zf.writestr("MAXWELL/UNIT DEC.TIF", b"a")
        zf.writestr("MAXWELL/UNIT DEC AMENDMENT.TIF", b"b")   # the Vol 574/830 amendment
        zf.writestr("MAXWELL/CAF.TIF", b"c")                  # cruft -> dropped
        zf.writestr("MAXWELL/LEGAL APPROVAL.TIF", b"d")       # cruft -> dropped
    foreign = tmp_path / "K1400235 (DECL OF POOLED UNIT - WIESE UNIT).zip"
    with zipfile.ZipFile(foreign, "w") as zf:
        zf.writestr("WIESE/UNIT DEC.TIF", b"x")
    ddr = tmp_path / "DDR.xlsx"; ddr.write_bytes(b"z")
    plan = build_plan_from_unit_folder(
        unit_name="MAXWELL A UNIT", ddr_path=ddr, files_dir=tmp_path,
        runsheet_rows=[], consumed_title_opinions=[],
        unit_dpu_contract="K1400813", archive_workdir=tmp_path / "work")
    placed = {p.dest_name for p in plan.for_subfolder(SUBFOLDERS[2])}
    assert placed == {"UNIT DEC.TIF", "UNIT DEC AMENDMENT.TIF"}   # amendment in, cruft out
    assert any("WIESE" in d and "another unit" in d.lower() for d in plan.decisions)


# --- Bug 2: TO used if referenced anywhere incl. notes / audit trail ---------

def test_opinion_cited_only_in_a_note_is_included(tmp_path):
    christie = tmp_path / "T0140456 (C.B. CHRISTIE JR. A-122 160ACS-TITLE OPINIONS).zip"
    gann = tmp_path / "T0140457 (RAY GANN ET AL A-122 160 ACS-TITLE OPINIONS).zip"
    unrelated = tmp_path / "T-O ORIG SOMEONE ELSE A-122.PDF"
    for p in (christie, gann, unrelated):
        p.write_bytes(b"x")
    # The DDR body never names these; only a NOTE cell does, by opinion number.
    ddr_texts = [
        "Ownership figures per operator report",
        "NOTE: Leases 0190122-007/-008 left blank per T0140456 and Ray Gann opinion.",
    ]
    used, unused = select_used_title_opinions([christie, gann, unrelated], ddr_texts)
    used_names = {p.name for p in used}
    assert christie.name in used_names            # matched by opinion number in a note
    assert gann.name in used_names                # matched by surname in a note
    assert unrelated.name not in used_names       # never referenced -> dropped
    assert any("SOMEONE" in p.name or "ELSE" in p.name for p, _ in unused)


def test_used_TO_archive_is_expanded_to_its_member_opinion(tmp_path):
    import zipfile
    # A zipped opinion the DDR cites by number, plus filing cruft to drop.
    z = tmp_path / "T0140456 (C.B. CHRISTIE JR. A-122 160ACS-TITLE OPINIONS).zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("T0140456/T-O SUPP C.B. CHRISTIE JR ET AL A-122 BLK 3 160AC.PDF", b"op")
        zf.writestr("T0140456/CAF.TIF", b"cruft")
        zf.writestr("T0140456/LEGAL APPROVAL.TIF", b"cruft")
    ddr = tmp_path / "DDR.xlsx"; ddr.write_bytes(b"x")
    plan = build_plan_from_unit_folder(
        unit_name="MAXWELL A UNIT", ddr_path=ddr, files_dir=tmp_path,
        runsheet_rows=[],
        ddr_texts=["NOTE: lease left blank per opinion T0140456."],
        archive_workdir=tmp_path / "work")
    placed = {p.dest_name for p in plan.for_subfolder(SUBFOLDERS[1])}
    assert placed == {"T-O SUPP C.B. CHRISTIE JR ET AL A-122 BLK 3 160AC.PDF"}  # PDF, not zip
    assert not any(n.lower().endswith(".zip") for n in placed)
    assert not any("CAF" in n or "LEGAL APPROVAL" in n for n in placed)


def test_unused_TO_archive_is_not_expanded_and_is_logged(tmp_path):
    import zipfile
    z = tmp_path / "T0140999 (SOMEONE UNCITED A-122-TITLE OPINIONS).zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("T0140999/T-O ORIG SOMEONE UNCITED A-122.PDF", b"op")
    ddr = tmp_path / "DDR.xlsx"; ddr.write_bytes(b"x")
    plan = build_plan_from_unit_folder(
        unit_name="MAXWELL A UNIT", ddr_path=ddr, files_dir=tmp_path,
        runsheet_rows=[], ddr_texts=["nothing relevant here"],
        archive_workdir=tmp_path / "work")
    assert plan.for_subfolder(SUBFOLDERS[1]) == []
    assert any("T0140999" in d and "never references" in d for d in plan.decisions)


def test_word_to_does_not_falsely_flag_a_seller_file_as_a_TO(tmp_path):
    # "ENCANA TO EOG" must not be read as a title-opinion marker.
    _touch(tmp_path, "K1400170 (FARMOUT AGMTASMT - ENCANA TO EOG-FARMOUT AGREEMENT).zip")
    b = classify_unit_files(tmp_path)
    assert not b["title_opinions"]
    assert any("FARMOUT" in p.name for p in b["sellers"])


# --- Bug 3: Leases folder holds member documents, not archives ---------------

def test_expand_archives_yields_members_not_the_zip(tmp_path):
    import zipfile
    z = tmp_path / "5 Leases.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("Lease A - Brashear.pdf", b"a")
        zf.writestr("Lease B - Ratliff.pdf", b"b")
        zf.writestr("Thumbs.db", b"junk")          # cruft, must be filtered
    out = expand_archives([z], tmp_path / "work")
    names = {p.name for p in out}
    assert names == {"Lease A - Brashear.pdf", "Lease B - Ratliff.pdf"}
    assert all(p.exists() for p in out)


def test_leases_folder_gets_extracted_members(tmp_path):
    import zipfile
    z = tmp_path / "5 Leases.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("Amendment 1.png", b"a")
        zf.writestr("Amendment 2.png", b"b")
    ddr = tmp_path / "DDR.xlsx"; ddr.write_bytes(b"x")
    plan = build_plan_from_unit_folder(
        unit_name="MAXWELL A UNIT", ddr_path=ddr, files_dir=tmp_path,
        runsheet_rows=[], consumed_title_opinions=[],
        archive_workdir=tmp_path / "work")
    lease_names = {p.dest_name for p in plan.for_subfolder(SUBFOLDERS[3])}
    assert lease_names == {"Amendment 1.png", "Amendment 2.png"}
    assert "5 Leases.zip" not in lease_names       # the archive itself is not placed


def test_build_plan_from_unit_folder_places_consumed_TO_only(tmp_path):
    _touch(tmp_path,
           "T-O ORIG BRUMBAUGH A-122 212.PDF",         # consumed
           "T-O ORIG RAY GANN A-122 160AC.PDF",        # present but NOT consumed
           "K1400813 (DECL OF POOLED UNIT - MAXWELL).zip")
    ddr = tmp_path / "DDR.xlsx"; ddr.write_bytes(b"x")
    plan = build_plan_from_unit_folder(
        unit_name="MAXWELL A UNIT", ddr_path=ddr, files_dir=tmp_path,
        consumed_title_opinions=["T-O ORIG BRUMBAUGH A-122 212"],
        runsheet_rows=[])
    tos = {p.source.name for p in plan.for_subfolder(SUBFOLDERS[1])}
    assert any("BRUMBAUGH" in n for n in tos)
    assert not any("RAY GANN" in n for n in tos)       # unused TO stays out
    assert len(plan.for_subfolder(SUBFOLDERS[2])) == 1  # DPU placed
