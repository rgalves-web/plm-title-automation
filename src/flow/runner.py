"""The wrapper that binds the flow spine to the DD engine.

Reads a unit's case file, derives the allowlist from its evidence ledger (never
hand-typed — assessment §3.1), runs the mandatory gates unchanged, and writes the
results back into the case file. The engine (validators, source-truth, pipeline)
is called, never modified: this layer sequences and feeds it, it never relaxes it
(blueprint §7).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from src.flow.config import Config, configure_tesseract
from src.flow.unit_state import UnitState, save_state


def build_allowlist(state: UnitState):
    """The engine's UnitAllowlist, computed from the ledger. This is the whole
    point of the spine: the allowlist is derived, so it can never drift stale."""
    from src.dd.ddr_validator import UnitAllowlist

    derived = state.derive_allowlist()
    return UnitAllowlist(
        unit_name=derived["unit_name"],
        leases=set(derived["leases"]),
        contracts=set(derived["contracts"]),
        title_opinions=set(derived["title_opinions"]),
        identity_tokens=set(derived["identity_tokens"]),
    )


def _unit_folder(state: UnitState) -> Path | None:
    if state.ddr_path:
        return Path(state.ddr_path).parent
    return None


def revalidate_from_state(
    state: UnitState,
    config: Config,
    *,
    template_path: str | Path | None = None,
    run_source_truth: bool = False,
    persist: bool = True,
    units_dir: str | Path | None = None,
) -> Any:
    """Re-run the mandatory gates for a unit using ONLY its case file.

    Structural gate always; source-truth gate when ``run_source_truth`` is set
    (slow OCR — configure the window via config). Records a compact gate summary
    into ``state.gate_results`` and, when ``persist``, saves the case file.
    Returns the engine's ValidationReport.

    Acceptance (blueprint §6): with a Maxwell state.yaml whose ledger holds the
    confirmed title-opinion chain, this reproduces 0 FAIL / 0 MISMATCH with a
    zero hand-built allowlist."""
    from src.dd.ddr_validator import run_final_validation

    if not state.ddr_path or not Path(state.ddr_path).exists():
        raise FileNotFoundError(
            f"state has no readable ddr_path ({state.ddr_path!r}); cannot validate")

    allowlist = build_allowlist(state)
    unit_folder = _unit_folder(state)
    template = template_path or config.template_path

    documents_available = None
    source_roots: tuple = ()
    if unit_folder is not None:
        from src.dd.dd_pipeline import _documents_on_disk, _validation_source_roots
        documents_available = _documents_on_disk(unit_folder)
        if run_source_truth:
            configure_tesseract(config)   # honest no-op if the binary is absent
            source_roots = tuple(_validation_source_roots(
                unit_folder, unit_folder / "FILES", None))

    report = run_final_validation(
        Path(state.ddr_path),
        template_path=template,
        allowlist=allowlist,
        documents_available=documents_available,
        client_name=(state.manifest_snapshot or {}).get("client_name"),
        source_roots=source_roots,
        run_source_truth_check=run_source_truth,
    )

    state.gate_results = _summarize(report, allowlist)
    if persist:
        save_state(state, units_dir or config.units_dir)
    return report


def _summarize(report: Any, allowlist: Any) -> dict[str, Any]:
    fails = [f for f in report.findings
             if str(getattr(f, "severity", "FAIL")).upper() == "FAIL"]
    pend = [f for f in report.findings
            if str(getattr(f, "severity", "")).upper() == "PENDING"]
    summary: dict[str, Any] = {
        "structural": {
            "ready": bool(getattr(report, "ready", False)),
            "fail": len(fails),
            "pending": len(pend),
            "summary": report.summary() if hasattr(report, "summary") else "",
        },
        "allowlist_derived": {
            "title_opinions": sorted(allowlist.title_opinions),
            "contracts": sorted(allowlist.contracts),
            "leases": len(allowlist.leases),
            "identity_tokens": sorted(allowlist.identity_tokens),
        },
    }
    truth = getattr(report, "truth", None)
    if truth is not None:
        mismatches = getattr(truth, "mismatches", []) or []
        summary["source_truth"] = {
            "mismatch": len(mismatches),
            "truthful": bool(getattr(truth, "truthful", not mismatches)),
            "summary": truth.summary() if hasattr(truth, "summary") else "",
        }
    return summary


def run_unit_from_state(
    state: UnitState,
    config: Config,
    *,
    template_path: str | Path | None = None,
    run_source_truth: bool = False,
    units_dir: str | Path | None = None,
    **pipeline_kwargs: Any,
) -> tuple[Any, Any]:
    """Thin wrapper over the full pipeline: run it to (re)write the DDR, then
    re-validate with the ledger-derived allowlist and record the gates in the
    case file. Returns (pipeline_result, validation_report).

    Pipeline inputs are passed through; the engine is unchanged."""
    from src.dd.dd_pipeline import run_dd_pipeline_for_unit

    result = run_dd_pipeline_for_unit(unit_name=state.unit_name, **pipeline_kwargs)
    ddr_out = getattr(getattr(result, "ddr_result", None), "output_path", None)
    if ddr_out:
        state.ddr_path = str(ddr_out)
    report = revalidate_from_state(
        state, config, template_path=template_path,
        run_source_truth=run_source_truth, persist=True, units_dir=units_dir)
    return result, report
