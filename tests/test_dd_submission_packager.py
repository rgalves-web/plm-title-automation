"""PLM Submission Packager: assemble the required Drive folder for a unit.

Every placed file must trace to a real document; anything expected-but-absent
goes to MISSING so the gap is visible, never hidden.
"""
from __future__ import annotations

from pathlib import Path

from src.dd.submission_packager import (
    SUBFOLDERS,
    build_plan_from_unit_folder,
    build_submission_plan,
    classify_unit_files,
    parse_vol_page,
    render_manifest,
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
