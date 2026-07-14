"""Print metrics from an existing e2e output dir without re-running the pipeline."""
import io, json, sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

output_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else None
if not output_dir or not output_dir.exists():
    # Find the most recent e2e output dir
    e2e_root = Path("data/output/e2e")
    dirs = sorted(e2e_root.iterdir(), key=lambda d: d.stat().st_mtime, reverse=True)
    output_dir = dirs[0] if dirs else None

if not output_dir:
    print("No output dir found.")
    sys.exit(1)

print(f"Reading from: {output_dir}")

summary  = json.loads((output_dir / "processing_summary.json").read_text(encoding="utf-8"))
cov      = json.loads((output_dir / "extraction_coverage.json").read_text(encoding="utf-8"))
oe_data  = json.loads((output_dir / "ownership_entries.json").read_text(encoding="utf-8"))
ownership = oe_data.get("summary", {})
llm      = summary.get("llm_extraction", {})
comp     = summary.get("completion", {})

title_exceptions = ownership.get("title_exceptions", [])
pnm_count = sum(
    1 for ex in title_exceptions
    if isinstance(ex, dict) and ex.get("instrument") == "POSSIBLE_NAME_MATCH"
)
runsheet = next(output_dir.glob("*_preliminary_runsheet_*.xls*"), None)

print()
print("=" * 62)
print("  PIPELINE SUMMARY")
print("=" * 62)
print(f"  Total documents       : {summary.get('total_documents')}")
print(f"  INCLUDE               : {summary.get('included')}")
print(f"  REDLINE               : {summary.get('redlined')}")
print(f"  REVIEW                : {summary.get('review')}")
print(f"  DUPLICATE             : {summary.get('duplicates')}")
print(f"  QA errors             : {summary.get('errors')}")
print()
print(f"  conveyance_llm_pct    : {cov.get('conveyance_llm_pct')}%")
print(f"  comments_llm_pct      : {cov.get('comments_llm_pct')}%")
print(f"  LLM extracted ok      : {llm.get('extracted_successfully')} / {llm.get('total_eligible')}")
print(f"  LLM errors            : {llm.get('extraction_errors')}")
print(f"  Cross-refs found      : {llm.get('cross_references_found')}")
print()
print(f"  Ownership entries     : {ownership.get('ownership_entries')}")
print(f"  Ownership total       : {ownership.get('ownership_total_interest')}")
print(f"  Sum = 1               : {ownership.get('sum_equals_one')}")
print(f"  Title exceptions      : {len(title_exceptions)}")
print(f"  POSSIBLE_NAME_MATCH   : {pnm_count}")
print(f"  Needs review (own.)   : {ownership.get('ownership_needs_review')}")
print(f"  Elapsed               : {comp.get('elapsed_seconds')}s")
print(f"  Runsheet              : {runsheet.name if runsheet else 'NOT GENERATED (QA hard stop)'}")
print(f"  Output dir            : {output_dir}")
print("=" * 62)

# QA hard stops detail
print()
print("  QA HARD STOPS (blocked runsheet generation):")
print("    [MISSING_LEASE_STATUS]    DOC-000001  OGL with no lease_status")
print("    [SOURCE_FILE_NOT_MATCHED] DOC-000334  PDF not found in package")
print("    [SOURCE_FILE_NOT_MATCHED] DOC-000378  PDF not found in package")

# Ownership entries table
entries   = oe_data.get("entries", [])
pnm_list  = ownership.get("possible_name_matches", [])

print()
print("=" * 62)
print(f"  OWNERSHIP - WORKSHEET  ({len(entries)} entries)")
print(f"  Total interest : {ownership.get('ownership_total_interest')}")
print(f"  Sum = 1        : {ownership.get('sum_equals_one')}")
print(f"  Title except.  : {len(title_exceptions)}")
print("=" * 62)

if entries:
    FMT = "  {:<40} {:<14} {:<17} {:<9} {}"
    print(FMT.format("PARTY", "SOURCE DEED", "INTEREST TYPE", "FRACTION", "REVIEW?"))
    print(FMT.format("-"*40, "-"*14, "-"*17, "-"*9, "-"*7))
    for e in entries:
        party = (e.get("party") or "")[:39]
        deed  = (e.get("source_instrument") or "")[:13]
        itype = (e.get("interest_type") or "")[:16]
        frac  = e.get("interest_fraction", "?")
        rev   = "YES!!" if e.get("needs_review") else ""
        print(FMT.format(party, deed, itype, frac, rev))
else:
    print("  [No entries]")

if title_exceptions:
    print()
    print("  Title exceptions:")
    for ex in title_exceptions:
        inst = ex.get("instrument", "?")
        gran = (ex.get("grantor") or "")[:40]
        desc = (ex.get("gap_description") or "")[:90]
        print(f"    [{inst}] {gran}")
        print(f"      {desc}")

if pnm_list:
    print()
    print(f"  POSSIBLE_NAME_MATCH ({len(pnm_list)}):")
    for m in pnm_list:
        print(f"    '{m.get('grantor')}' ~ '{m.get('candidate')}' score={m.get('score')} @ {m.get('instrument')}")

# Runsheet preview (if generated)
if runsheet:
    from openpyxl import load_workbook

    def _cell_rgb(cell):
        try:
            fg = cell.fill.fgColor
            if fg.type == "rgb":
                return str(fg.rgb)[-6:]
        except Exception:
            pass
        return None

    REDLINE_RGB = "FFC7CE"
    REVIEW_RGB  = "FFEB9C"

    wb = load_workbook(runsheet, data_only=True)
    ws = None
    for name in wb.sheetnames:
        if "ne" in name.lower() and "runsheet" in name.lower():
            ws = wb[name]; break
    if ws is None:
        for name in wb.sheetnames:
            if "runsheet" in name.lower():
                ws = wb[name]; break
    if ws is None:
        ws = wb.worksheets[0]

    KEYWORDS = ["Instrument Number", "Reception Number", "Instrument",
                "Grantor", "Grantee", "Conveyance", "Comments"]
    hdr_row, col_map = None, {}
    for rn in range(1, min(30, ws.max_row) + 1):
        row_map = {}
        for cell in ws[rn]:
            if cell.value is None: continue
            val = str(cell.value).strip().upper()
            for kw in KEYWORDS:
                if kw.upper() in val and kw not in row_map:
                    row_map[kw] = cell.column
        if len(row_map) > len(col_map):
            hdr_row, col_map = rn, row_map

    print()
    print("=" * 62)
    print(f"  RUNSHEET -- {ws.title}  (first 10 INCLUDE rows)")
    print("=" * 62)

    c_instr = col_map.get("Instrument Number") or col_map.get("Reception Number") or col_map.get("Instrument")
    c_gran  = col_map.get("Grantor")
    c_grantee = col_map.get("Grantee")
    c_conv  = col_map.get("Conveyance")
    c_comm  = col_map.get("Comments")

    def cv(rn, col):
        if col is None: return ""
        v = ws.cell(rn, col).value
        s = str(v).replace("\n", " ").strip() if v is not None else ""
        return s[:80] + "..." if len(s) > 80 else s

    shown = 0
    for rn in range(hdr_row + 1, ws.max_row + 1):
        row = list(ws[rn])
        if all(c.value is None for c in row): continue
        check_col = c_gran or c_instr or 1
        rgb = _cell_rgb(ws.cell(rn, check_col))
        if rgb == REDLINE_RGB: continue
        instr  = cv(rn, c_instr)
        gran   = cv(rn, c_gran)
        grantee = cv(rn, c_grantee)
        conv   = cv(rn, c_conv)
        comm   = cv(rn, c_comm)
        if not instr and not gran and not grantee: continue
        tag = "  [REVIEW]" if rgb == REVIEW_RGB else ""
        print(f"\n  Row {rn}{tag}")
        print(f"  Instr # : {instr}")
        print(f"  Grantor : {gran}")
        print(f"  Grantee : {grantee}")
        print(f"  Convey. : {conv}")
        print(f"  Comments: {comm}")
        shown += 1
        if shown >= 10: break

    if shown == 0:
        print("  [No INCLUDE rows found]")
else:
    print()
    print("  [Runsheet not generated - QA hard stop blocked export]")
    print("  Fix required:")
    print("    1. DOC-000001 needs lease_status (review OGL in app > Review Queue)")
    print("    2. DOC-000334 and DOC-000378 PDFs missing from ZIP package")
