"""MOR pipeline exposed as a tool — a thin wrapper, no pipeline changes.

Adapts a folder + assignment into the real ``src.pipeline.run_full_pipeline``
call: it locates the document-list workbook and the runsheet template in the
folder, passes an optional document package, and normalizes the PipelineResult
into the artifact shape the orchestrator stores.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

from src.agent.registry import Tool

ProgressCb = Callable[[str, str], None]

_TEMPLATE_RE = re.compile(r"template|runsheet", re.IGNORECASE)
_DOCLIST_RE = re.compile(r"document.?list|doc.?list|documents", re.IGNORECASE)


def enumerate_mor_inputs(folder: Path) -> tuple[Path | None, Path | None, Path | None]:
    """Return (document_list, template, document_package). Heuristic by name:
    a workbook whose name says 'template'/'runsheet' is the template; the other
    workbook is the document list; a .zip is the document package."""
    document_list = template = package = None
    workbooks = []
    for path in sorted(folder.rglob("*")):
        if path.is_dir():
            continue
        suffix = path.suffix.lower()
        if suffix == ".zip" and package is None:
            package = path
        elif suffix in (".xlsx", ".xls", ".csv"):
            if _TEMPLATE_RE.search(path.name) and template is None:
                template = path
            else:
                workbooks.append(path)
    for wb in workbooks:
        if _DOCLIST_RE.search(wb.name):
            document_list = wb
            break
    if document_list is None and workbooks:
        document_list = workbooks[0]
    return document_list, template, package


def run_mor_tool(params: dict[str, Any], progress: ProgressCb | None = None) -> dict[str, Any]:
    from src.pipeline import run_full_pipeline

    folder = Path(params["folder_path"])
    output_root = Path(params.get("output_root", "data/output"))
    document_list, template, package = enumerate_mor_inputs(folder)
    document_list = Path(params["document_list_path"]) if params.get("document_list_path") else document_list
    template = Path(params["template_path"]) if params.get("template_path") else template

    if document_list is None:
        return {"status": "failed", "error": "No document-list workbook found in the folder.",
                "artifacts": [], "output_dir": None, "summary": ""}
    if template is None:
        return {"status": "failed", "error": "No runsheet template workbook found in the folder.",
                "artifacts": [], "output_dir": None, "summary": ""}

    metadata = {
        "project_name": params.get("project_name") or folder.name,
        "county": params.get("county", "UNKNOWN"),
        "state": params.get("state", "TX"),
    }
    if progress:
        progress("working", f"Running MOR on {document_list.name} …")
    result = run_full_pipeline(
        document_list_path=document_list,
        template_path=template,
        metadata=metadata,
        output_root=output_root,
        document_package_path=package,
    )
    artifacts = [str(p) for p in result.artifacts.values()]
    return {
        "status": "done",
        "summary": f"{len(result.records)} records; "
                   f"{sum(1 for e in result.qa_exceptions if e.severity == 'ERROR')} QA errors.",
        "artifacts": artifacts,
        "output_dir": str(result.output_dir),
        "error": None,
    }


MOR_TOOL = Tool(
    name="mor_pipeline",
    description="Master Ownership Report: classify a document list and write a preliminary runsheet + QA workbooks.",
    run=run_mor_tool,
    param_schema={
        "folder_path": "local folder containing the document-list workbook, the runsheet template, and optional document package",
        "project_name": "optional project name (default: folder name)",
        "county": "optional county",
        "output_root": "optional output directory (default data/output)",
    },
)
