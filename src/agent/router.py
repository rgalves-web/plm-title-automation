"""Deterministic intent router: folder + one-sentence assignment -> a Route.

No LLM in Phase 1. The pipeline is decided from folder *signatures* (what kinds
of files are present) plus keyword hints in the instruction. When both or
neither pipeline clearly fits, the route is marked ``needs_confirmation`` with a
human-readable reason — the orchestrator then asks rather than guessing.

DD signature: a DDR template workbook, and/or title-opinion PDFs, and/or the
reference workbooks (Project Log / Lease-to-Well XREF / Well List).
MOR signature: a document-list workbook + a runsheet template (no DD reference
workbooks), and/or a document-package zip.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# Unit-name convention: "<NAME> UNIT". Extracted by walking back from the word
# UNIT over unit-like tokens, stopping at instruction stopwords — so
# "run confirmatory title for BOWEN A UNIT" yields "BOWEN A UNIT", not the
# whole clause.
_UNIT_STOPWORDS = {
    "FOR", "THE", "RUN", "TITLE", "CONFIRMATORY", "SUPPLEMENTAL", "DUE",
    "DILIGENCE", "DD", "PROCESS", "THIS", "OF", "ON", "IN", "AND", "A_UNIT",
    "BUILD", "DDR", "REVIEW", "DO",
}
_TO_NAME_RE = re.compile(r"(^T0\d{4,})|(\bT[\-\s]?O\b)|(TITLE\s+OPINION)", re.IGNORECASE)
_DDR_TEMPLATE_RE = re.compile(r"ddr.*template|template.*ddr", re.IGNORECASE)
_MOR_TEMPLATE_RE = re.compile(r"runsheet|template", re.IGNORECASE)
_DOCLIST_RE = re.compile(r"document.?list|doc.?list", re.IGNORECASE)
_DD_REFERENCE_HINTS = ("project log", "lease to well", "xref", "well list")
_DD_WORD = re.compile(r"\b(due diligence|ddr|title opinion|supplemental title|reconcil)\b", re.IGNORECASE)
_MOR_WORD = re.compile(r"\b(runsheet|document list|ownership report|classif|redline)\b", re.IGNORECASE)


@dataclass
class Route:
    pipeline: str | None  # "dd_pipeline" | "mor_pipeline" | None
    unit_name: str | None
    task: str
    needs_confirmation: bool
    reason: str
    signals: dict[str, bool] = field(default_factory=dict)

    @property
    def tool_name(self) -> str | None:
        return self.pipeline


def _folder_signals(folder: Path) -> dict[str, bool]:
    has_ddr_template = has_to_pdf = has_dd_reference = False
    has_doclist = has_mor_template = has_package = False
    for path in folder.rglob("*"):
        if path.is_dir():
            continue
        name = path.name
        suffix = path.suffix.lower()
        lower = name.lower()
        if suffix == ".zip":
            has_package = True
        if suffix in (".xlsx", ".xlsm", ".xls", ".csv"):
            if _DDR_TEMPLATE_RE.search(name):
                has_ddr_template = True
            if any(h in lower for h in _DD_REFERENCE_HINTS):
                has_dd_reference = True
            if _DOCLIST_RE.search(name):
                has_doclist = True
            if _MOR_TEMPLATE_RE.search(name) and not _DDR_TEMPLATE_RE.search(name):
                has_mor_template = True
        if suffix == ".pdf" and _TO_NAME_RE.search(name):
            has_to_pdf = True
    return {
        "ddr_template": has_ddr_template,
        "title_opinion_pdf": has_to_pdf,
        "dd_reference_workbook": has_dd_reference,
        "document_list": has_doclist,
        "mor_template": has_mor_template,
        "document_package": has_package,
    }


def _unit_from_text(text: str) -> str | None:
    tokens = re.findall(r"[A-Za-z0-9&\-]+", (text or "").upper())
    for i, tok in enumerate(tokens):
        if tok != "UNIT":
            continue
        name = ["UNIT"]
        j = i - 1
        while j >= 0 and tokens[j] not in _UNIT_STOPWORDS and len(tokens[j]) <= 15 and (i - j) <= 4:
            name.insert(0, tokens[j])
            j -= 1
        if len(name) >= 2:
            return " ".join(name)
    return None


def _extract_unit(instruction: str, folder: Path) -> str | None:
    return _unit_from_text(instruction) or _unit_from_text(folder.name)


def route(folder_path: str | Path, instruction: str = "") -> Route:
    folder = Path(folder_path)
    if not folder.exists() or not folder.is_dir():
        return Route(None, None, instruction.strip(), True,
                     f"Folder does not exist or is not a directory: {folder}")

    sig = _folder_signals(folder)
    dd_score = sum(sig[k] for k in ("ddr_template", "title_opinion_pdf", "dd_reference_workbook"))
    mor_score = sum(sig[k] for k in ("document_list", "mor_template", "document_package"))

    # Instruction keywords nudge, but folder evidence dominates.
    if _DD_WORD.search(instruction or ""):
        dd_score += 1
    if _MOR_WORD.search(instruction or ""):
        mor_score += 1

    unit = _extract_unit(instruction, folder)
    task = (instruction or "").strip() or "process folder"

    if dd_score and dd_score > mor_score:
        return Route("dd_pipeline", unit, task, False,
                     f"DD signals ({dd_score}) outweigh MOR ({mor_score}); "
                     f"unit={unit or 'all'}.", sig)
    if mor_score and mor_score > dd_score:
        return Route("mor_pipeline", unit, task, False,
                     f"MOR signals ({mor_score}) outweigh DD ({dd_score}).", sig)

    if dd_score == 0 and mor_score == 0:
        return Route(None, unit, task, True,
                     "No recognizable DD or MOR inputs in the folder "
                     "(no DDR template, title opinions, reference workbooks, "
                     "document list, or package).", sig)
    return Route(None, unit, task, True,
                 f"Ambiguous: DD and MOR signals tied ({dd_score}={mor_score}). "
                 "Confirm which pipeline to run.", sig)
