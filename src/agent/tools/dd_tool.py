"""DD pipeline exposed as a tool — a thin wrapper, no pipeline changes.

Adapts a local folder path + one-sentence assignment into the real
``src.dd.dd_upload_runner.run_dd_upload`` call: it enumerates the folder's PDFs
and workbooks (extracting any zips, mirroring app.py's behavior), finds the DDR
template, and normalizes the pipeline result into the artifact shape the
orchestrator stores.
"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Any, Callable

from src.agent.registry import Tool

ProgressCb = Callable[[str, str], None]

_DDR_TEMPLATE_RE = re.compile(r"ddr.*template|template.*ddr", re.IGNORECASE)


def enumerate_dd_inputs(folder: Path, extract_dir: Path) -> tuple[list[Path], Path | None]:
    """Return (document_paths, ddr_template_path). PDFs and workbooks are
    collected recursively; zips are extracted so their PDFs join the pile
    (same convention as the Streamlit uploader)."""
    document_paths: list[Path] = []
    template: Path | None = None
    for path in sorted(folder.rglob("*")):
        if path.is_dir():
            continue
        suffix = path.suffix.lower()
        if suffix == ".zip":
            document_paths.extend(_extract_pdfs(path, extract_dir / path.stem))
        elif suffix in (".pdf",):
            document_paths.append(path)
        elif suffix in (".xlsx", ".xlsm"):
            if template is None and _DDR_TEMPLATE_RE.search(path.name):
                template = path
            else:
                document_paths.append(path)
    return document_paths, template


def _extract_pdfs(zip_path: Path, dest: Path) -> list[Path]:
    dest.mkdir(parents=True, exist_ok=True)
    out: list[Path] = []
    try:
        with zipfile.ZipFile(zip_path) as zf:
            for info in zf.infolist():
                if info.is_dir() or not info.filename.lower().endswith(".pdf"):
                    continue
                target = dest / Path(info.filename).name
                if not target.exists():
                    with zf.open(info) as src, target.open("wb") as fh:
                        fh.write(src.read())
                out.append(target)
    except zipfile.BadZipFile:
        pass
    return out


def run_dd_tool(params: dict[str, Any], progress: ProgressCb | None = None) -> dict[str, Any]:
    from src.dd.dd_upload_runner import run_dd_upload

    folder = Path(params["folder_path"])
    output_root = Path(params.get("output_root", "data/output/dd"))
    instructions = params.get("instructions_text", "")
    unit_name = params.get("unit_name")

    template_path = params.get("ddr_template_path")
    extract_dir = output_root / "_agent_extracted"
    document_paths, discovered_template = enumerate_dd_inputs(folder, extract_dir)
    template_path = Path(template_path) if template_path else discovered_template
    if template_path is None:
        return {"status": "failed", "error": "No DDR template (…DDR…template….xlsx) found in the folder.",
                "artifacts": [], "output_dir": None, "summary": ""}
    if not document_paths:
        return {"status": "failed", "error": "No PDFs or workbooks found in the folder.",
                "artifacts": [], "output_dir": None, "summary": ""}

    result = run_dd_upload(
        document_paths=document_paths,
        ddr_template_path=template_path,
        output_root=output_root,
        instructions_text=instructions,
        progress_callback=progress,
        unit_name_filter=unit_name,
    )

    if getattr(result, "fatal_error", None):
        return {"status": "failed", "error": result.fatal_error, "artifacts": [],
                "output_dir": str(output_root), "summary": ""}

    artifacts: list[str] = []
    unit_lines: list[str] = []
    for outcome in result.unit_outcomes:
        if outcome.error:
            unit_lines.append(f"{outcome.unit_name}: FAILED — {outcome.error}")
            continue
        ddr = outcome.result.ddr_result.output_path
        artifacts.append(str(ddr))
        s = outcome.result.summary
        unit_lines.append(
            f"{outcome.unit_name}: {s.get('title_opinions_total', '?')} TO(s), "
            f"WI {s.get('reconciliation_wi_status')}, NRI {s.get('reconciliation_nri_status')}"
        )
    status = "done" if artifacts else "failed"
    return {
        "status": status,
        "summary": "; ".join(unit_lines) or "No units produced.",
        "artifacts": artifacts,
        "output_dir": str(output_root),
        "error": None if artifacts else "No DDR produced.",
    }


DD_TOOL = Tool(
    name="dd_pipeline",
    description="Due Diligence: build per-unit DDR(s) from a folder of title opinions + reference workbooks + DDR template.",
    run=run_dd_tool,
    param_schema={
        "folder_path": "local folder containing TO PDFs, Project Log/XREF/Well List, and the DDR template",
        "unit_name": "optional unit to process (e.g. 'BOWEN A UNIT'); blank runs all units",
        "instructions_text": "one-sentence assignment / instructions",
        "output_root": "optional output directory (default data/output/dd)",
    },
)
