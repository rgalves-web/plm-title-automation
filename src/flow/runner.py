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
    """The unit's PROJECT folder — the ancestor of the DDR that holds FILES.

    A deliverable can sit nested inside a submission tree (Bowen:
    <unit>/Bowen A Unit/1. Landman Submitted/PLM Report/DDR….xlsx), so the
    DDR's immediate parent is NOT the unit root. Walking up to the first
    ancestor containing a FILES folder finds the real root; pointing the
    source index at the wrong folder silently yields 0 confirmed cells —
    an artifact, not a verdict."""
    if not state.ddr_path:
        return None
    ddr = Path(state.ddr_path)
    for ancestor in ddr.parents:
        if (ancestor / "FILES").exists():
            return ancestor
    return ddr.parent


def revalidate_from_state(
    state: UnitState,
    config: Config,
    *,
    template_path: str | Path | None = None,
    run_source_truth: bool = False,
    persist: bool = True,
    units_dir: str | Path | None = None,
    as_of: Any = None,
) -> Any:
    """Re-run the mandatory gates for a unit using ONLY its case file.

    as_of: date the submission-date rule judges against. None = real today
    (send-time semantics). Regressions over an already-shipped deliverable pin
    it to the shipped date, so a past date is not a manufactured FAIL.

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

    declared_sheets = {e["name"]: e.get("reason", "")
                       for e in state.declared_exclusions
                       if e.get("kind") == "sheet" and e.get("name")}
    report = run_final_validation(
        Path(state.ddr_path),
        template_path=template,
        allowlist=allowlist,
        documents_available=documents_available,
        client_name=(state.manifest_snapshot or {}).get("client_name"),
        source_roots=source_roots,
        run_source_truth_check=run_source_truth,
        declared_sheet_exclusions=declared_sheets or None,
        as_of=as_of,
        write_sidecar=False,     # written below, AFTER the human rulings apply
    )
    apply_sanctions(report, state.sanctions)
    # Now the report reflects the verdict (declared exclusions + sanctions), so
    # the sidecar can be truthful. A replay never writes: re-validating a
    # shipped unit must not mutate the delivered folder.
    if as_of is None:
        from src.dd.ddr_validator import write_validation_sidecar
        write_validation_sidecar(report, Path(state.ddr_path))

    state.gate_results = _summarize(report, allowlist)
    if persist:
        save_state(state, units_dir or config.units_dir)
    return report


def sanction_key(finding: Any) -> str:
    return f"{getattr(finding, 'sheet', '')}!{getattr(finding, 'cell', '')}:{getattr(finding, 'rule', '')}"


def apply_sanctions(report: Any, sanctions: dict[str, dict[str, str]]) -> list[Any]:
    """Downgrade FAIL findings the landman explicitly sanctioned to SANCTIONED.

    A sanction is per-finding (sheet!cell:rule) and carries the human's reason.
    It applies ONLY while the finding's value is unchanged — the sanction stores
    a value snapshot, and a changed cell voids it, so a sanction can never mask
    new content. The matcher itself is untouched: unsanctioned findings on any
    other cell keep failing exactly as before."""
    if not sanctions:
        return []
    import dataclasses
    applied = []
    for i, f in enumerate(report.findings):
        if str(getattr(f, "severity", "")).upper() != "FAIL":
            continue
        s = sanctions.get(sanction_key(f))
        if s is None:
            continue
        if str(s.get("value", ""))[:60] != str(getattr(f, "value", ""))[:60]:
            continue                     # value changed since the human ruled
        text = (f"SANCTIONED by {s.get('by', 'landman')}: {s.get('reason', '')} "
                f"[was: {f.expected}]")
        try:
            new = dataclasses.replace(f, severity="SANCTIONED", expected=text)
        except TypeError:                # plain object (tests) — mutate in place
            f.severity = "SANCTIONED"
            f.expected = text
            new = f
        report.findings[i] = new
        applied.append(new)
    return applied


def _summarize(report: Any, allowlist: Any) -> dict[str, Any]:
    fails = [f for f in report.findings
             if str(getattr(f, "severity", "FAIL")).upper() == "FAIL"]
    pend = [f for f in report.findings
            if str(getattr(f, "severity", "")).upper() == "PENDING"]
    declared = [f for f in report.findings
                if str(getattr(f, "severity", "")).upper() == "DECLARED"]
    sanctioned = [f for f in report.findings
                  if str(getattr(f, "severity", "")).upper() == "SANCTIONED"]
    summary: dict[str, Any] = {
        "structural": {
            "ready": bool(getattr(report, "ready", False)),
            "fail": len(fails),
            "pending": len(pend),
            "declared": len(declared),
            "sanctioned": len(sanctioned),
            "declared_items": [f.describe() for f in declared],
            "sanctioned_items": [f.describe() for f in sanctioned],
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
