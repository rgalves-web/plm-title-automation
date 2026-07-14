"""End-to-end pipeline run + runsheet validation for section 4S-64W-15.

Runs the full pipeline (intake → OCR → LLM → ownership → runsheet) and
prints a structured report:
  1. Pipeline summary metrics
  2. First 10 INCLUDE rows from Runsheet - NE
  3. All rows from Ownership - Worksheet (via ownership_entries.json)

Usage:
    python scripts/run_section_e2e.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from openpyxl import load_workbook

from src.intake import read_document_list_from_package
from src.pipeline import build_extraction_coverage, run_full_pipeline_from_dataframe
from src.qa import QAHardStopError
from src.schemas import ClassificationStatus, ProjectMetadata

# ── Config ────────────────────────────────────────────────────────────────────

PKG = Path("data/input/document_packages/4S-64W-15-20260602T114641Z-3-001.zip")
TEMPLATE = next(iter(sorted(Path("data/working/uploads").glob("*.xlsx"))), None)
OUTPUT_ROOT = Path("data/output/e2e")

META = ProjectMetadata(
    project_name="4S-64W-15",
    county="Arapahoe",
    state="Colorado",
    section="15",
    township="4S",
    range="64W",
)

REDLINE_RGB = "FFC7CE"
REVIEW_RGB  = "FFEB9C"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _cell_rgb(cell) -> str | None:
    try:
        fg = cell.fill.fgColor
        if fg.type == "rgb":
            return str(fg.rgb)[-6:]
    except Exception:
        pass
    return None


def _find_header_row(ws, keywords: list[str], max_rows: int = 30):
    """Return (row_num, {keyword: col_idx}) for the row matching most keywords."""
    best_row, best_map = None, {}
    for rn in range(1, min(max_rows, ws.max_row) + 1):
        row_map: dict[str, int] = {}
        for cell in ws[rn]:
            if cell.value is None:
                continue
            val = str(cell.value).strip().upper()
            for kw in keywords:
                if kw.upper() in val and kw not in row_map:
                    row_map[kw] = cell.column
        if len(row_map) > len(best_map):
            best_row, best_map = rn, row_map
    return best_row, best_map


def _trunc(val, n: int) -> str:
    if val is None:
        return ""
    s = str(val).replace("\n", " ").strip()
    return s[:n] + "..." if len(s) > n else s


# ── Pipeline run ──────────────────────────────────────────────────────────────

def run_pipeline():
    pdl = read_document_list_from_package(PKG)
    result, hard_stop_exc, output_dir = None, None, None

    try:
        result = run_full_pipeline_from_dataframe(
            dataframe=pdl.dataframe,
            template_path=TEMPLATE,
            metadata=META,
            output_root=str(OUTPUT_ROOT),
            source_file_name=pdl.member_name,
            document_package_path=PKG,
            llm_extraction=True,
        )
        output_dir = result.output_dir
    except QAHardStopError as exc:
        hard_stop_exc = exc
        # Find the directory the pipeline created before raising
        dirs = sorted(
            OUTPUT_ROOT.iterdir(), key=lambda d: d.stat().st_mtime, reverse=True
        ) if OUTPUT_ROOT.exists() else []
        output_dir = dirs[0] if dirs else None
        print(f"\n!! QA HARD STOP:{len(exc.exceptions)} error(s):")
        for e in exc.exceptions[:20]:
            print(f"   [{e.code}] {e.source_document_id or 'GLOBAL'}: {e.message}")

    return result, hard_stop_exc, output_dir


# ── Metrics summary ───────────────────────────────────────────────────────────

def print_metrics(result, output_dir: Path, elapsed: float):
    summary = {}
    records = []
    if result:
        summary = result.summary
        records = result.records
    if not summary and output_dir:
        ps = output_dir / "processing_summary.json"
        if ps.exists():
            summary = json.loads(ps.read_text(encoding="utf-8"))

    cov: dict = {}
    if records:
        cov = build_extraction_coverage(records)
    elif output_dir:
        ec = output_dir / "extraction_coverage.json"
        if ec.exists():
            cov = json.loads(ec.read_text(encoding="utf-8"))

    # Ownership may be absent from summary if pipeline hard-stopped before 2nd write
    ownership = summary.get("ownership", {})
    if not ownership and output_dir:
        oe_path = output_dir / "ownership_entries.json"
        if oe_path.exists():
            oe_data = json.loads(oe_path.read_text(encoding="utf-8"))
            ownership = oe_data.get("summary", {})
    llm       = summary.get("llm_extraction", {})
    comp      = summary.get("completion", {})

    include_full = (
        sum(1 for r in records if r.status == ClassificationStatus.INCLUDE_FULL)
        if records else summary.get("included", "?")
    )

    title_exceptions = ownership.get("title_exceptions", [])
    pnm_count = sum(
        1 for ex in title_exceptions
        if isinstance(ex, dict) and ex.get("instrument") == "POSSIBLE_NAME_MATCH"
    )

    runsheet = next(output_dir.glob("*_preliminary_runsheet_*.xls*"), None) if output_dir else None

    print()
    print("=" * 62)
    print("  PIPELINE SUMMARY")
    print("=" * 62)
    print(f"  Total documents       : {summary.get('total_documents', '?')}")
    print(f"  INCLUDE (full+limited): {include_full}")
    print(f"  REDLINE               : {summary.get('redlined', '?')}")
    print(f"  REVIEW                : {summary.get('review', '?')}")
    print(f"  DUPLICATE             : {summary.get('duplicates', '?')}")
    print(f"  QA errors             : {summary.get('errors', '?')}")
    print()
    print(f"  conveyance_llm_pct    : {cov.get('conveyance_llm_pct', '?')}%")
    print(f"  comments_llm_pct      : {cov.get('comments_llm_pct', '?')}%")
    print(f"  LLM extracted ok      : {llm.get('extracted_successfully', '?')}/{llm.get('total_eligible', '?')}")
    print(f"  LLM errors            : {llm.get('extraction_errors', '?')}")
    print(f"  Cross-refs found      : {llm.get('cross_references_found', '?')}")
    print()
    print(f"  Ownership entries     : {ownership.get('ownership_entries', '?')}")
    print(f"  Ownership total       : {ownership.get('ownership_total_interest', '?')}")
    print(f"  Sum = 1               : {ownership.get('sum_equals_one', '?')}")
    print(f"  Title exceptions      : {len(title_exceptions)}")
    print(f"  POSSIBLE_NAME_MATCH   : {pnm_count}")
    print(f"  Needs review (own.)   : {ownership.get('ownership_needs_review', '?')}")
    print()
    print(f"  Elapsed               : {elapsed:.1f}s")
    print(f"  Runsheet              : {runsheet.name if runsheet else 'NOT GENERATED'}")
    print(f"  Output dir            : {output_dir}")
    print("=" * 62)


# ── Runsheet - NE preview ─────────────────────────────────────────────────────

def print_runsheet_preview(output_dir: Path):
    runsheet = next(output_dir.glob("*_preliminary_runsheet_*.xls*"), None)
    if not runsheet:
        print("\n[Runsheet not found — skipping preview]")
        return

    wb = load_workbook(runsheet, data_only=True)
    # Prefer "Runsheet - NE", fall back to first runsheet-like sheet
    ws = None
    for name in wb.sheetnames:
        if "ne" in name.lower() and "runsheet" in name.lower():
            ws = wb[name]
            break
    if ws is None:
        for name in wb.sheetnames:
            if "runsheet" in name.lower():
                ws = wb[name]
                break
    if ws is None:
        ws = wb.worksheets[0]

    KEYWORDS = [
        "Instrument Number", "Reception Number", "Instrument",
        "Grantor", "Grantee", "Conveyance", "Comments",
    ]
    hdr_row, col_map = _find_header_row(ws, KEYWORDS)
    if not hdr_row:
        print(f"\n[Could not locate header row in sheet '{ws.title}']")
        return

    c_instr = col_map.get("Instrument Number") or col_map.get("Reception Number") or col_map.get("Instrument")
    c_gran  = col_map.get("Grantor")
    c_gran_e = col_map.get("Grantee")
    c_conv  = col_map.get("Conveyance")
    c_comm  = col_map.get("Comments")

    def cv(rn, col):
        if col is None:
            return ""
        v = ws.cell(rn, col).value
        return str(v).strip() if v is not None else ""

    print()
    print("=" * 62)
    print(f"  RUNSHEET — {ws.title}  (first 10 INCLUDE rows)")
    print("=" * 62)

    shown = 0
    for rn in range(hdr_row + 1, ws.max_row + 1):
        # Skip completely empty rows
        row = list(ws[rn])
        if all(c.value is None for c in row):
            continue
        # Detect fill via the grantor or instrument column
        check_col = c_gran or c_instr or 1
        rgb = _cell_rgb(ws.cell(rn, check_col))
        if rgb == REDLINE_RGB:
            continue  # skip REDLINE rows

        instr = cv(rn, c_instr)
        gran  = cv(rn, c_gran)
        gran_e = cv(rn, c_gran_e)
        conv  = cv(rn, c_conv)
        comm  = cv(rn, c_comm)

        if not instr and not gran and not gran_e:
            continue

        tag = "  [REVIEW]" if rgb == REVIEW_RGB else ""
        print(f"\n  Row {rn}{tag}")
        print(f"  Instr # : {_trunc(instr, 30)}")
        print(f"  Grantor : {_trunc(gran, 80)}")
        print(f"  Grantee : {_trunc(gran_e, 80)}")
        print(f"  Convey. : {_trunc(conv, 80)}")
        print(f"  Comments: {_trunc(comm, 80)}")
        shown += 1
        if shown >= 10:
            break

    if shown == 0:
        print("  [No INCLUDE rows found in this sheet]")


# ── Ownership - Worksheet preview ─────────────────────────────────────────────

def print_ownership_preview(output_dir: Path):
    oe_path = output_dir / "ownership_entries.json"
    if not oe_path.exists():
        print("\n[ownership_entries.json not found — skipping]")
        return

    oe      = json.loads(oe_path.read_text(encoding="utf-8"))
    entries = oe.get("entries", [])
    excepts = oe.get("exceptions", [])
    summary = oe.get("summary", {})
    pnm     = summary.get("possible_name_matches", [])

    print()
    print("=" * 62)
    print(f"  OWNERSHIP - WORKSHEET  ({len(entries)} entries)")
    print(f"  Total interest : {summary.get('ownership_total_interest', '?')}")
    print(f"  Sum = 1        : {summary.get('sum_equals_one', '?')}")
    print(f"  Title except.  : {len(excepts)}")
    print("=" * 62)

    if not entries:
        print("  [No entries — no INCLUDE_FULL records with conveyance found]")
    else:
        FMT = "  {:<42} {:<14} {:<17} {:<9} {}"
        print(FMT.format("PARTY", "SOURCE DEED", "INTEREST TYPE", "FRACTION", "REVIEW?"))
        print(FMT.format("-" * 42, "-" * 14, "-" * 17, "-" * 9, "-" * 7))
        for e in entries:
            party = _trunc(e.get("party"), 41)
            deed  = _trunc(e.get("source_instrument"), 13)
            itype = _trunc(e.get("interest_type"), 16)
            frac  = e.get("interest_fraction", "?")
            rev   = "YES!!" if e.get("needs_review") else ""
            print(FMT.format(party, deed, itype, frac, rev))

    if excepts:
        print()
        print("  Title exceptions:")
        for ex in excepts:
            inst = ex.get("instrument", "?")
            gran = ex.get("grantor", "")
            desc = _trunc(ex.get("gap_description", ""), 100)
            print(f"    [{inst}] {gran} — {desc}")

    if pnm:
        print()
        print(f"  POSSIBLE_NAME_MATCH ({len(pnm)}):")
        for m in pnm:
            print(f"    '{m.get('grantor')}' ≈ '{m.get('candidate')}' "
                  f"score={m.get('score')} @ {m.get('instrument')}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not set.", file=sys.stderr)
        sys.exit(1)
    if not PKG.exists():
        print(f"ERROR: Package not found: {PKG}", file=sys.stderr)
        sys.exit(1)
    if TEMPLATE is None or not TEMPLATE.exists():
        print("ERROR: No template found in data/working/uploads/", file=sys.stderr)
        sys.exit(1)

    print(f"Package  : {PKG.name}")
    print(f"Template : {TEMPLATE.name}")
    print("Running full pipeline - this may take a few minutes...")

    t0 = time.monotonic()
    result, hard_stop_exc, output_dir = run_pipeline()
    elapsed = time.monotonic() - t0

    if output_dir is None:
        print(f"\nElapsed: {elapsed:.1f}s — no output directory found.")
        sys.exit(1)

    print_metrics(result, output_dir, elapsed)
    print_runsheet_preview(output_dir)
    print_ownership_preview(output_dir)


if __name__ == "__main__":
    # Force UTF-8 output on Windows so Unicode chars don't crash
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    main()
