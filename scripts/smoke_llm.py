"""Smoke test: LLM extraction on the first 15 eligible records of a real package.

Usage:
    $env:ANTHROPIC_API_KEY = "sk-ant-..."
    python scripts/smoke_llm.py data/input/document_packages/<package>.zip
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from src.classifier import classify_documents
from src.dedupe import deduplicate_documents
from src.document_register import create_document_register
from src.intake import read_document_list_from_package
from src.pdf_reader import TEXT_EXTRACTED
from src.pipeline import build_extraction_coverage, run_llm_extraction, run_source_verification
from src.schemas import ProjectMetadata
from src.source_matcher import requires_source_reading


def main(pkg_path: str) -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: Set ANTHROPIC_API_KEY before running.", file=sys.stderr)
        sys.exit(1)

    pkg = Path(pkg_path)
    if not pkg.exists():
        print(f"ERROR: File not found: {pkg}", file=sys.stderr)
        sys.exit(1)

    out = Path("data/output/smoke_llm")
    out.mkdir(parents=True, exist_ok=True)

    meta = ProjectMetadata(
        project_name=pkg.stem,
        county="Arapahoe",
        state="Colorado",
        section="15",
        township="4S",
        range="64W",
    )
    pdl = read_document_list_from_package(pkg)
    records = create_document_register(
        pdl.dataframe, metadata=meta, source_file_name=pdl.member_name
    )
    deduplicate_documents(records)
    classify_documents(records)

    # Stable selection: sorted by source_document_id, first 15 eligible records
    eligible_ids = [
        r.source_document_id
        for r in sorted(records, key=lambda r: r.source_document_id)
        if requires_source_reading(r)
    ][:15]
    target_ids = set(eligible_ids)
    subset = [r for r in records if r.source_document_id in target_ids]
    # Sort subset in the same stable order for consistent output
    subset.sort(key=lambda r: r.source_document_id)

    print(f"Selected {len(subset)} records (stable, sorted by ID):")
    for doc_id in eligible_ids:
        print(f"  {doc_id}")
    print()

    print(f"Source verification (OCR) on {len(subset)} records...")
    run_source_verification(subset, output_dir=out, metadata=meta, document_package_path=pkg)

    eligible = [r for r in subset if r.pdf_extraction_status == TEXT_EXTRACTED]
    print(f"LLM extraction on {len(eligible)} TEXT_EXTRACTED records...")
    llm_metrics = run_llm_extraction(subset, output_dir=out, metadata=meta)

    cov = build_extraction_coverage(subset)
    json_out = out / "extraction_coverage.json"
    json_out.write_text(json.dumps({**cov, "llm_metrics": llm_metrics}, indent=2), encoding="utf-8")

    print("\n=== extraction_coverage.json ===")
    print(json.dumps(cov, indent=2))
    print("\n=== LLM metrics ===")
    print(json.dumps(llm_metrics, indent=2))

    print("\n=== Sample rows ===")
    shown = 0
    for r in subset:
        if not r.llm_extraction_model:
            continue
        print(f"\n{r.source_document_id} | {r.document_type}")
        print(f"  CONVEYANCE (conf={r.llm_conveyance_confidence}):")
        print(f"    {(r.conveyance or '')[:160]}")
        print(f"  COMMENTS   (conf={r.llm_comments_confidence}):")
        print(f"    {(r.comments or '')[:160]}")
        shown += 1
        if shown >= 15:
            break

    print(f"\nDone. Coverage: conveyance_llm_pct={cov.get('conveyance_llm_pct')}%")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/smoke_llm.py <package.zip>", file=sys.stderr)
        sys.exit(1)
    main(sys.argv[1])
