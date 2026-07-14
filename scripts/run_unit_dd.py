"""CLI entry point for the Due Diligence (DDR) pipeline, one unit at a time.

Usage:
    python scripts/run_unit_dd.py "BOWEN A UNIT"
    python scripts/run_unit_dd.py "BOWEN A UNIT" --to-files-dir "data/input/dd/_reference/title_opinions"

Defaults point at data/input/dd/_reference/, mirroring the data/input/sample/
convention used by the MOR path.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from src.dd.dd_pipeline import SupplementalScopeError, run_dd_pipeline_for_unit

REFERENCE_DIR = Path("data/input/dd/_reference")
DEFAULT_PROJECT_LOG = REFERENCE_DIR / "BKV122TX - Project Log.xlsx"
DEFAULT_XREF = REFERENCE_DIR / "Lease to Well XREF.xlsx"
DEFAULT_WELL_LIST = REFERENCE_DIR / "Well List with Prelim AV% directional estimates.xlsx"
DEFAULT_TEMPLATE = REFERENCE_DIR / "DDR - Template (PLM).xlsx"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the DD/DDR pipeline for one unit.")
    parser.add_argument("unit_name", help='Unit name as it appears in the Project Log, e.g. "BOWEN A UNIT"')
    parser.add_argument("--project-log", type=Path, default=DEFAULT_PROJECT_LOG)
    parser.add_argument("--xref", type=Path, default=DEFAULT_XREF)
    parser.add_argument("--well-list", type=Path, default=DEFAULT_WELL_LIST)
    parser.add_argument("--ddr-template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--to-files-dir", type=Path, default=None, help="Directory of title opinion zip files, if available.")
    parser.add_argument("--output-root", type=Path, default=Path("data/output/dd"))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    for label, path in (
        ("Project Log", args.project_log),
        ("Lease to Well XREF", args.xref),
        ("Well List", args.well_list),
        ("DDR template", args.ddr_template),
    ):
        if not path.exists():
            print(f"ERROR: {label} not found at {path}", file=sys.stderr)
            return 1

    print(f"Unit          : {args.unit_name}")
    print(f"Project Log   : {args.project_log.name}")
    print(f"XREF          : {args.xref.name}")
    print(f"Well List     : {args.well_list.name}")
    print(f"DDR Template  : {args.ddr_template.name}")
    print("Running DD pipeline...")

    try:
        result = run_dd_pipeline_for_unit(
            unit_name=args.unit_name,
            project_log_path=args.project_log,
            xref_path=args.xref,
            well_list_path=args.well_list,
            ddr_template_path=args.ddr_template,
            output_root=args.output_root,
            to_files_dir=args.to_files_dir,
        )
    except SupplementalScopeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Manifest      : {result.manifest_path}")
    print(f"DDR output    : {result.ddr_result.output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
