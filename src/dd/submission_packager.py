"""PLM Submission Packager — assemble the Drive folder a unit submission needs.

PLM's coordinator requires a fixed folder structure for every unit handed off to
the reviewers. Building it by hand is the kind of clerical step that gets a
document filed in the wrong bucket, a duplicate title opinion shipped, or an
instrument silently dropped. This stage assembles it mechanically from what the
pipeline already knows — the DDR, its audit trail, the runsheet, and the unit's
FILES folder — and writes a manifest that accounts for every file placed and,
crucially, every file EXPECTED BUT NOT FOUND. A gap is listed, never hidden.

    <Unit Name, Title Case>/
      1. Landman Submitted/
        1. PLM Report/        the DDR .xlsx
        2. Title Opinions/    one unique copy of each TO the DDR actually used
        3. Unit Designation/  the DPU covering the well + amendments
        4. Leases/            the unit's lease / amendment documents
        5. Title Documents/    every runsheet instrument, renamed "volume.page"
        6. Seller's Files/    ONLY source-cited materials (Farmout/JOA, assignments)
        7. Well Files/        the RRC production report, or empty with a note

Two disciplines carried over from the rest of the pipeline: never invent a file
(every placed file traces to a real document in FILES; anything absent goes to
MISSING), and be conservative about Seller's Files (if it was not cited as a
source, it does not go in — division orders, bonus receipts, lease-acquisition
reports and summaries are excluded by name).

The plan builder (`build_submission_plan`) is pure and takes explicit inputs, so
it is fully testable; `stage_submission` does the disk IO.
"""
from __future__ import annotations

import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

# The seven subfolders, in submission order.
SUBFOLDERS = (
    "1. PLM Report",
    "2. Title Opinions",
    "3. Unit Designation",
    "4. Leases",
    "5. Title Documents",
    "6. Seller's Files",
    "7. Well Files",
)
LANDMAN_SUBMITTED = "1. Landman Submitted"
MANIFEST_NAME = "SUBMISSION_MANIFEST.txt"

# Words a unit name keeps upper/lower against naive title-casing.
_UPPER_TOKENS = {"A", "B", "C", "D", "I", "II", "III", "IV", "AOG", "EOG", "BKV"}
_LOWER_TOKENS = {"OF", "THE", "AND"}


def title_case_unit_name(name: str) -> str:
    """"MAXWELL A UNIT" -> "Maxwell A Unit". Not str.title(): the unit letter "A"
    stays "A", not "a", and joining words lower-case."""
    words = str(name).split()
    out = []
    for i, word in enumerate(words):
        upper = word.upper()
        if upper in _UPPER_TOKENS:
            out.append(upper)
        elif upper in _LOWER_TOKENS and i not in (0, len(words) - 1):
            out.append(upper.lower())
        else:
            out.append(word[:1].upper() + word[1:].lower())
    return " ".join(out)


# Seller's Files: keep source-relevant instruments, drop the extraneous.
_SELLER_EXCLUDE_RE = re.compile(
    r"\b(division order|\bd\.?o\.?\b|bonus receipt|lease acquisition|"
    r"\blar\b|lease summary|summary of lease|caf|legal approval|notes?|"
    r"proposal|payment election|calculation)\b", re.IGNORECASE)
_SELLER_INCLUDE_RE = re.compile(
    r"\b(farmout|farm.out|joa|joint operating|assignment|asmt|conveyance|"
    r"bill of sale|ratification)\b", re.IGNORECASE)

# Recorded-instrument volume/page, however the runsheet prints it.
_VOL_PAGE_RE = re.compile(
    r"\b(?:vol(?:ume)?|book|bk)\.?\s*(\d+)\D{0,14}?(?:p(?:a)?g(?:e)?)\.?\s*(\d+)\b",
    re.IGNORECASE)


@dataclass(frozen=True)
class PlacedFile:
    subfolder: str
    source: Path
    dest_name: str
    note: str = ""


@dataclass(frozen=True)
class MissingItem:
    subfolder: str
    what: str
    reason: str


@dataclass
class SubmissionPlan:
    unit_name: str
    unit_title: str
    placed: list[PlacedFile] = field(default_factory=list)
    missing: list[MissingItem] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)   # dedupe / exclusion notes

    def for_subfolder(self, subfolder: str) -> list[PlacedFile]:
        return [p for p in self.placed if p.subfolder == subfolder]


# ---------------------------------------------------------------------------
# Helpers over a file inventory
# ---------------------------------------------------------------------------

def _norm(text: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "", str(text).upper())


def parse_vol_page(text: str) -> tuple[str, str] | None:
    """"Doc 95850, OPR Vol. 492, Pg. 510" -> ("492", "510")."""
    m = _VOL_PAGE_RE.search(str(text or ""))
    return (m.group(1), m.group(2)) if m else None


_PAGE_CITE_RE = re.compile(r"\bpp?\.\s*\d", re.IGNORECASE)   # " pp.5-6", " p. 3"


def _to_key(name: str) -> str:
    """Normalise a title-opinion reference/filename so the same opinion under
    two spellings collapses to one key for deduplication. Drops a trailing page
    cite ("pp.5-6", "p. 3") — any case — so a bare name and a page-cited
    reference to the same opinion share a key."""
    stem = _PAGE_CITE_RE.split(str(name), maxsplit=1)[0]
    stem = Path(stem).stem
    return _norm(stem)


# Boilerplate that carries no identity in a title-opinion name — dropped when
# reducing a name to its tract-chain key so two spellings of the same opinion
# ("KRAMER MINERAL TRUST EL AL" vs "... ET AL") land on the same key.
_TO_STOP = {
    "TO", "ORIG", "SUPP", "DO", "MINERAL", "MINERALS", "TRUST", "LIMITED", "LTD",
    "ET", "AL", "EL", "AND", "THE", "UNIT", "BLK", "BLOCK", "LEAGUE", "REVISED",
    "MIN", "PART", "ACS", "AC", "ETAL", "FROM", "AOG", "PLM",
}


def _chain_key(name: str) -> str:
    """A title opinion's tract-chain identity: its ORIG/SUPP/DO stage plus the
    party surname(s), stripped of boilerplate and legal-description tail. Two
    file-drop copies of the same opinion under different names ("BLK 7 22.333AC"
    vs "LEAGUE 12 22.3333AC") share a chain key; an Original and its Supplement
    do NOT (different stage), so both are kept. Empty when nothing survives."""
    stem = _PAGE_CITE_RE.split(str(name), maxsplit=1)[0]
    stem = Path(stem).stem
    upper = stem.upper()
    stage = "SUPP" if re.search(r"\bSUPP", upper) else (
        "DO" if re.search(r"\bDO\b", upper) else "ORIG")
    head = re.split(r"A-?\d{2,}", upper, maxsplit=1)[0]      # drop at abstract no.
    parties = sorted({t for t in re.findall(r"[A-Z]{3,}", head) if t not in _TO_STOP})
    return f"{stage}|{','.join(parties)}" if parties else ""


# ---------------------------------------------------------------------------
# The plan
# ---------------------------------------------------------------------------

def _unit_core_tokens(unit_name: str) -> set[str]:
    """The distinctive words of a unit name — drops "UNIT" and the single-letter
    designator so "MAXWELL A UNIT" -> {"MAXWELL"}. Used to tell the unit's own
    Declaration of Pooled Unit from a foreign unit's."""
    return {t for t in re.findall(r"[A-Z]{3,}", str(unit_name).upper())
            if t not in {"UNIT", "THE", "AND"}}


def _dpu_is_own_unit(name: str, unit_name: str, unit_dpu_contract: str | None) -> bool:
    """True if this designation belongs to THIS unit — it carries the unit's own
    DPU contract number, or names the unit (all core tokens present). The latter
    catches an amendment filed under a different contract number."""
    nn = _norm(name)
    own_contract = _norm(unit_dpu_contract) if unit_dpu_contract else ""
    core = _unit_core_tokens(unit_name)
    return (bool(own_contract) and own_contract in nn) or (
        bool(core) and all(_norm(t) in nn for t in core))


# Filing cruft that rides along inside a recorded-document archive but is never
# part of the substantive package (checklist approval forms, transmittals, notes).
_FILING_CRUFT_RE = re.compile(
    r"\bCAF\b|LEGAL APPROVAL|TRANSMITTAL|\bNOTES?\b|PROPOSAL", re.IGNORECASE)


def _is_document_member(member_name: str) -> bool:
    """A recognised document type that is not filing cruft — the common gate for
    expanding any recorded-instrument archive."""
    return (Path(member_name).suffix.lower() in _DOC_MEMBER_EXTS
            and not _FILING_CRUFT_RE.search(member_name))


# Which members of a DPU archive belong in Unit Designation: the declaration and
# its amendments, NOT the filing cruft.
def _dpu_member_filter(member_name: str) -> bool:
    return (_is_document_member(member_name)
            and bool(re.search(r"UNIT DEC|DECLARATION|DESIGNAT|POOLED",
                               member_name, re.IGNORECASE)))


# Which members of a title-opinion archive belong in Title Opinions: the opinion
# documents themselves, minus the same filing cruft.
def _to_member_filter(member_name: str) -> bool:
    return _is_document_member(member_name)


def build_submission_plan(
    unit_name: str,
    ddr_path: Path | None,
    consumed_title_opinions: Iterable[str],
    dpu_files: Iterable[Path],
    lease_files: Iterable[Path],
    runsheet_rows: Iterable[dict[str, Any]],
    sellers_files: Iterable[Path],
    well_files: Iterable[Path],
    file_index: dict[str, Path],
    unit_dpu_contract: str | None = None,
    filter_dpu: bool = True,
) -> SubmissionPlan:
    """Decide what goes where — pure, no disk writes.

    consumed_title_opinions: names/refs of the TOs the DDR actually used (from
        the audit trail); resolved against file_index and DEDUPED.
    file_index: normalised-key -> Path over the unit's FILES folder, for
        resolving a TO reference or a runsheet vol/page to a real document.
    runsheet_rows: dicts with at least {instrument, source_ref} — source_ref
        carries the "Vol X, Pg Y" the file is renamed from.
    unit_dpu_contract: the unit's OWN DPU contract number (e.g. "K1400813").
        Only this unit's designation and its amendments go in Unit Designation;
        a DPU for any other unit is excluded with a logged decision.
    """
    plan = SubmissionPlan(unit_name=unit_name, unit_title=title_case_unit_name(unit_name))

    # 1. PLM Report — the DDR.
    if ddr_path and Path(ddr_path).exists():
        plan.placed.append(PlacedFile(SUBFOLDERS[0], Path(ddr_path), Path(ddr_path).name))
    else:
        plan.missing.append(MissingItem(SUBFOLDERS[0], "the unit DDR .xlsx",
                                        "no finished DDR path supplied or file absent"))

    # 2. Title Opinions — one unique copy of each TO used, deduped. Two guards:
    # by opinion key (a bare name and its page-cited twin collapse) AND by the
    # resolved physical file (never ship the same PDF twice, however it was
    # cited).
    seen: dict[str, Path] = {}
    seen_paths: dict[str, Path] = {}
    seen_chains: dict[str, Path] = {}
    for ref in consumed_title_opinions:
        key = _to_key(ref)
        path = _resolve(ref, file_index)
        if path is None:
            plan.missing.append(MissingItem(SUBFOLDERS[1], f"title opinion {ref!r}",
                                            "cited by the DDR but no file found in FILES"))
            continue
        if key in seen:
            plan.decisions.append(f"Title Opinions: deduped {ref!r} — same opinion as "
                                  f"{seen[key].name!r} already placed")
            continue
        path_key = _norm(str(path))
        if path_key in seen_paths:
            plan.decisions.append(f"Title Opinions: deduped {ref!r} — resolves to the same file "
                                  f"{seen_paths[path_key].name!r} already placed")
            continue
        chain = _chain_key(path.name) or _chain_key(ref)
        if chain and chain in seen_chains:
            plan.decisions.append(
                f"Title Opinions: deduped {path.name!r} — appears to be the same opinion "
                f"({chain}) as {seen_chains[chain].name!r} already placed (verify)")
            continue
        seen[key] = path
        seen_paths[path_key] = path
        if chain:
            seen_chains[chain] = path
        plan.placed.append(PlacedFile(SUBFOLDERS[1], path, path.name))

    # 3. Unit Designation — the unit's OWN DPU + amendments, nothing else. A
    # foreign unit's designation (e.g. a neighbouring Wiese Unit DPU that shares
    # the FILES folder) is excluded and the exclusion logged. filter_dpu=False
    # means the caller already vetted ownership (e.g. it expanded the own DPU
    # archive into members that no longer carry the unit's name) — then place all.
    for path in _dedupe_paths(dpu_files):
        if filter_dpu and not _dpu_is_own_unit(path.name, unit_name, unit_dpu_contract):
            plan.decisions.append(
                f"Unit Designation: excluded {path.name!r} — a designation for another "
                f"unit, not {plan.unit_title}'s own DPU"
                + (f" ({unit_dpu_contract})" if unit_dpu_contract else ""))
            continue
        is_amend = bool(re.search(r"AMEND", path.name, re.IGNORECASE))
        note = "amendment to this unit's DPU" if is_amend else ""
        plan.placed.append(PlacedFile(SUBFOLDERS[2], path, path.name, note=note))
    if not plan.for_subfolder(SUBFOLDERS[2]):
        plan.missing.append(MissingItem(SUBFOLDERS[2], "the Declaration of Pooled Unit",
                                        "no DPU document located for this unit"))

    # 4. Leases — the unit's lease / amendment documents.
    for path in _dedupe_paths(lease_files):
        plan.placed.append(PlacedFile(SUBFOLDERS[3], path, path.name))

    # 5. Title Documents — every runsheet instrument, renamed volume.page.
    used_dest: set[str] = set()
    for i, row in enumerate(runsheet_rows, start=1):
        source_ref = str(row.get("source_ref") or row.get("instrument_number") or "")
        instrument = str(row.get("instrument") or f"row {i}")
        vp = parse_vol_page(source_ref)
        if vp is None:
            plan.missing.append(MissingItem(
                SUBFOLDERS[4], f"runsheet #{i}: {instrument[:40]}",
                f"no volume/page parseable from {source_ref[:40]!r}"))
            continue
        path = _resolve_vol_page(vp, file_index)
        dest = f"{vp[0]}.{vp[1]}"
        if path is None:
            plan.missing.append(MissingItem(
                SUBFOLDERS[4], f"instrument Vol {vp[0]} Pg {vp[1]} ({instrument[:34]})",
                "recorded in the runsheet but no source file found on disk"))
            continue
        dest_name = _unique_dest(f"{dest}{path.suffix.lower()}", used_dest)
        plan.placed.append(PlacedFile(SUBFOLDERS[4], path, dest_name,
                                      note=f"renamed from {path.name!r} ({instrument[:30]})"))

    # 6. Seller's Files — ONLY source-relevant, conservative.
    for path in _dedupe_paths(sellers_files):
        name = path.name
        if _SELLER_EXCLUDE_RE.search(name):
            plan.decisions.append(f"Seller's Files: excluded {name!r} — extraneous "
                                  "(division order / receipt / LAR / summary)")
            continue
        if not _SELLER_INCLUDE_RE.search(name):
            plan.decisions.append(f"Seller's Files: excluded {name!r} — not a source-cited "
                                  "instrument (conservative: when in doubt, leave out)")
            continue
        plan.placed.append(PlacedFile(SUBFOLDERS[5], path, name))

    # 7. Well Files — RRC report if any, else a visible note.
    well = list(_dedupe_paths(well_files))
    for path in well:
        plan.placed.append(PlacedFile(SUBFOLDERS[6], path, path.name))
    if not well:
        plan.missing.append(MissingItem(
            SUBFOLDERS[6], "RRC production report for the subject well",
            "not found on disk — coordinator may reassign Well Files to reviewers"))
    return plan


def _resolve(ref: str, file_index: dict[str, Path]) -> Path | None:
    key = _to_key(ref)
    if key in file_index:
        return file_index[key]
    for candidate_key, path in file_index.items():
        if key and (key in candidate_key or candidate_key in key):
            return path
    return None


def _resolve_vol_page(vp: tuple[str, str], file_index: dict[str, Path]) -> Path | None:
    """A file whose name encodes this vol/page (e.g. already "492.510.pdf",
    or a name containing "Vol 492 Pg 510")."""
    want = f"{vp[0]}.{vp[1]}"
    for key, path in file_index.items():
        if _norm(want) in key:
            return path
        pv = parse_vol_page(path.name)
        if pv == vp:
            return path
    return None


def _dedupe_paths(paths: Iterable[Path]) -> list[Path]:
    seen: dict[str, Path] = {}
    for path in paths:
        seen.setdefault(_norm(Path(path).stem), Path(path))
    return list(seen.values())


def _unique_dest(name: str, used: set[str]) -> str:
    if name not in used:
        used.add(name)
        return name
    stem, suffix = name.rsplit(".", 1) if "." in name else (name, "")
    i = 2
    while f"{stem} ({i}).{suffix}" in used:
        i += 1
    unique = f"{stem} ({i}).{suffix}"
    used.add(unique)
    return unique


# ---------------------------------------------------------------------------
# Staging + manifest
# ---------------------------------------------------------------------------

def render_manifest(plan: SubmissionPlan) -> str:
    lines = [
        f"PLM SUBMISSION MANIFEST — {plan.unit_title}",
        f"(source unit name: {plan.unit_name})",
        "",
        f"Root: {plan.unit_title}/{LANDMAN_SUBMITTED}/",
        f"Files placed: {len(plan.placed)}   Missing: {len(plan.missing)}   "
        f"Decisions: {len(plan.decisions)}",
        "",
        "== FILES PLACED ==",
    ]
    for sub in SUBFOLDERS:
        placed = plan.for_subfolder(sub)
        lines.append(f"  {sub}/  ({len(placed)})")
        for p in placed:
            note = f"   [{p.note}]" if p.note else ""
            lines.append(f"      {p.dest_name}   <- {p.source.name}{note}")
        if not placed:
            lines.append("      (empty)")
    lines.append("")
    lines.append("== DEDUPE / EXCLUSION DECISIONS ==")
    if plan.decisions:
        lines.extend(f"  - {d}" for d in plan.decisions)
    else:
        lines.append("  (none)")
    lines.append("")
    lines.append("== MISSING (expected but not found — visible, never hidden) ==")
    if plan.missing:
        for m in plan.missing:
            lines.append(f"  [{m.subfolder}] {m.what} — {m.reason}")
    else:
        lines.append("  (nothing missing)")
    return "\n".join(lines)


def stage_submission(plan: SubmissionPlan, output_root: Path, copy: bool = True) -> Path:
    """Create the folder tree under output_root and copy files in. Returns the
    unit root. Client files are copied (never moved) into a staging tree for the
    landman to review before uploading — nothing leaves the machine here."""
    output_root = Path(output_root)
    root = output_root / plan.unit_title / LANDMAN_SUBMITTED
    for sub in SUBFOLDERS:
        (root / sub).mkdir(parents=True, exist_ok=True)
    if copy:
        for p in plan.placed:
            dest = root / p.subfolder / p.dest_name
            if p.source.exists():
                shutil.copy2(p.source, dest)
    (root / MANIFEST_NAME).write_text(render_manifest(plan), encoding="utf-8")
    return root


# ---------------------------------------------------------------------------
# Convenience: assemble the inputs by scanning a unit's FILES folder
# ---------------------------------------------------------------------------

# Bucket a FILES-folder document by its name. These are deliberately narrow —
# when a name matches nothing, the file is simply not placed (conservative), so
# a wrong guess never smuggles an extraneous document into the package.
# A title-opinion filename marker. The separator between T and O is REQUIRED so
# the English word "to" ("ENCANA TO EOG") never matches — only "T-O" / "T O",
# "TITLE OPINION", or an opinion number "T0140456".
_TO_NAME_RE = re.compile(r"\bT[-\s]O\b|TITLE OPINION|\bT0\d{6}\b", re.IGNORECASE)
_TO_NUMBER_RE = re.compile(r"\bT0\d{6}\b", re.IGNORECASE)
# Archive members worth extracting into a document folder (skip thumbnails,
# desktop.ini, and other packaging cruft).
_DOC_MEMBER_EXTS = {".pdf", ".tif", ".tiff", ".png", ".jpg", ".jpeg", ".docx", ".doc"}
_DPU_NAME_RE = re.compile(
    r"\bDPU\b|POOLED UNIT|UNIT DESIGNAT|DECL(?:ARATION)?\s+OF\s+POOLED", re.IGNORECASE)
_WELL_NAME_RE = re.compile(
    r"\bRRC\b|PRODUCTION|COMPLETION REPORT|\bW-?2\b|\bP-?4\b|\bG-?1\b", re.IGNORECASE)
_LEASE_NAME_RE = re.compile(r"\bLEASE(?:S)?\b|\bOGML\b|\bO\.?G\.?M\.?L\b", re.IGNORECASE)
# Reference workbooks, other units' deliverables, cross-reference sheets — never
# part of THIS unit's submission.
_NOISE_NAME_RE = re.compile(
    r"\bXREF\b|LEASE TO WELL|CONTRACT XREF|\bDDR\b|\.xlsx?$", re.IGNORECASE)


def classify_unit_files(files_dir: Path, recurse: bool = True) -> dict[str, Any]:
    """Scan a unit's FILES folder and sort documents into the packager's buckets
    by filename. Returns {file_index, title_opinions, dpu, leases, sellers,
    wells}. The title_opinions bucket is the set of CANDIDATE opinions in the
    folder; which ones actually ship is decided against the DDR text (an opinion
    the DDR never references is dropped, with a logged decision).

    A file that matches no bucket is left out on purpose; the manifest's MISSING
    and DECISIONS sections make any such gap visible rather than silent.
    """
    files_dir = Path(files_dir)
    paths = (p for p in (files_dir.rglob("*") if recurse else files_dir.glob("*"))
             if p.is_file())
    file_index: dict[str, Path] = {}
    title_opinions: list[Path] = []
    dpu: list[Path] = []
    leases: list[Path] = []
    sellers: list[Path] = []
    wells: list[Path] = []
    for path in sorted(paths, key=lambda p: str(p)):
        file_index.setdefault(_norm(path.stem), path)
        name = path.name
        if _NOISE_NAME_RE.search(name):
            continue                                   # reference/other-unit noise
        if _DPU_NAME_RE.search(name):
            dpu.append(path)
        elif _WELL_NAME_RE.search(name):
            wells.append(path)
        elif _TO_NAME_RE.search(name):
            title_opinions.append(path)                # candidate — vetted vs DDR
        elif _SELLER_INCLUDE_RE.search(name) and not _SELLER_EXCLUDE_RE.search(name):
            sellers.append(path)                       # farmout / JOA / assignment
        elif _LEASE_NAME_RE.search(name):
            leases.append(path)
    return {"file_index": file_index, "title_opinions": title_opinions, "dpu": dpu,
            "leases": leases, "sellers": sellers, "wells": wells}


def expand_archives(
    paths: Iterable[Path],
    dest_dir: Path,
    member_filter: Callable[[str], bool] | None = None,
) -> list[Path]:
    """Extract every .zip in `paths` into `dest_dir` (namespaced by the archive
    stem) and return the member document paths; non-archive paths pass through
    unchanged. PLM wants the individual lease documents in the Leases folder,
    not the archive they arrived in, so a zip is replaced by its members.

    member_filter decides which members survive; the default keeps recognised
    document types and drops packaging cruft (thumbnails, desktop.ini)."""
    if member_filter is None:
        member_filter = lambda n: Path(n).suffix.lower() in _DOC_MEMBER_EXTS
    dest_dir = Path(dest_dir)
    out: list[Path] = []
    for path in paths:
        path = Path(path)
        if path.suffix.lower() == ".zip" and zipfile.is_zipfile(path):
            target_root = dest_dir / path.stem
            with zipfile.ZipFile(path) as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    member = Path(info.filename).name
                    if not member or not member_filter(member):
                        continue
                    target_root.mkdir(parents=True, exist_ok=True)
                    target = target_root / member
                    with zf.open(info) as src, open(target, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    out.append(target)
        else:
            out.append(path)
    return out


def _to_reference_tokens(name: str) -> list[str]:
    """The tokens that would identify this title opinion in DDR text: its opinion
    number (T0######) and its distinctive party surname(s)."""
    tokens: list[str] = [m.group(0).upper() for m in _TO_NUMBER_RE.finditer(name)]
    stem = Path(name).stem.upper()
    head = re.split(r"A-?\d{2,}", stem, maxsplit=1)[0]
    tokens += [t for t in re.findall(r"[A-Z]{4,}", head)
               if t not in _TO_STOP and t not in {"TITLE", "OPINIONS", "OPINION"}]
    return tokens


def select_used_title_opinions(
    candidates: Iterable[Path],
    ddr_texts: Iterable[str],
) -> tuple[list[Path], list[tuple[Path, str]]]:
    """Split candidate opinions into (used, unused). An opinion is USED if any of
    its identifying tokens — opinion number or party surname — appears anywhere
    in the DDR text, which INCLUDES notes and the audit trail, not just report
    cells. That is what catches an opinion cited only as the note-basis of a
    decision (e.g. the Alamo Christie/Gann opinions grounding a blank lease).
    Returns (used_paths, [(unused_path, reason), ...])."""
    blob = "\n".join(str(t).upper() for t in ddr_texts if t is not None)
    used: list[Path] = []
    unused: list[tuple[Path, str]] = []
    for path in candidates:
        tokens = _to_reference_tokens(path.name)
        hit = next((t for t in tokens if re.search(rf"\b{re.escape(t)}\b", blob)), None)
        if hit:
            used.append(path)
        else:
            unused.append((path, "present in FILES but the DDR never references it "
                                 f"(looked for {tokens or ['(no identifying token)']})"))
    return used, unused


def build_plan_from_unit_folder(
    unit_name: str,
    ddr_path: Path | None,
    files_dir: Path,
    runsheet_rows: Iterable[dict[str, Any]],
    ddr_texts: Iterable[str] | None = None,
    consumed_title_opinions: Iterable[str] | None = None,
    unit_dpu_contract: str | None = None,
    archive_workdir: Path | None = None,
    recurse: bool = True,
) -> SubmissionPlan:
    """Build a submission plan from a unit's FILES folder plus what only the
    finished DDR knows: its runsheet rows and its full text (cells + notes +
    audit trail). The DPU / Leases / Seller's Files / Well Files buckets are
    inferred from the folder by `classify_unit_files`.

    Title opinions are chosen by vetting the folder's candidate opinions against
    `ddr_texts` — an opinion referenced anywhere in the DDR (including a note or
    the audit trail) is shipped; one the DDR never references is dropped with a
    logged decision. Pass `consumed_title_opinions` to override that vetting with
    an explicit list. Lease archives are expanded into their member documents so
    the Leases folder holds individual leases, not zips."""
    b = classify_unit_files(files_dir, recurse=recurse)
    file_index = b["file_index"]
    workdir = Path(archive_workdir) if archive_workdir else Path(tempfile.mkdtemp(prefix="plm_pkg_"))

    # Title Opinions: vet candidates against the DDR text at the ARCHIVE level
    # (the archive name carries the opinion number the DDR cites), THEN expand a
    # used archive into its member opinion document(s) so a zipped opinion ships
    # as the PDF, not the zip. Members are registered in the file index so the
    # plan's resolve/dedup logic operates on the real documents.
    to_decisions: list[str] = []
    if consumed_title_opinions is not None:
        consumed = list(consumed_title_opinions)
    else:
        used, unused = select_used_title_opinions(b["title_opinions"], ddr_texts or [])
        to_members = expand_archives(used, workdir / "title_opinions", member_filter=_to_member_filter)
        for m in to_members:
            file_index.setdefault(_norm(m.stem), m)
        consumed = [m.name for m in to_members]
        to_decisions = [f"Title Opinions: excluded {p.name!r} — {why}" for p, why in unused]

    # Unit Designation: keep only this unit's own DPU, then expand it into its
    # declaration + amendment documents (dropping CAF / legal-approval cruft).
    # A foreign unit's designation is dropped with a logged decision.
    own_dpu, foreign_dpu = [], []
    for p in b["dpu"]:
        (own_dpu if _dpu_is_own_unit(p.name, unit_name, unit_dpu_contract) else foreign_dpu).append(p)
    dpu_decisions = [
        f"Unit Designation: excluded {p.name!r} — a designation for another unit, not "
        f"{title_case_unit_name(unit_name)}'s own DPU"
        + (f" ({unit_dpu_contract})" if unit_dpu_contract else "")
        for p in foreign_dpu
    ]
    dpu_members = expand_archives(own_dpu, workdir / "dpu", member_filter=_dpu_member_filter)

    lease_files = expand_archives(b["leases"], workdir / "leases")

    plan = build_submission_plan(
        unit_name=unit_name,
        ddr_path=ddr_path,
        consumed_title_opinions=consumed,
        dpu_files=dpu_members,
        lease_files=lease_files,
        runsheet_rows=runsheet_rows,
        sellers_files=b["sellers"],
        well_files=b["wells"],
        file_index=file_index,
        unit_dpu_contract=unit_dpu_contract,
        filter_dpu=False,          # ownership already vetted above
    )
    plan.decisions.extend(dpu_decisions)
    plan.decisions.extend(to_decisions)
    return plan
