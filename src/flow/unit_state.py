"""Canonical per-unit case file — the state the whole flow hangs off.

One ``state.yaml`` per unit at ``<units_dir>/<UNIT>/state.yaml``, versioned: every
save writes a retained ``state.v<N>.yaml`` snapshot alongside the latest. This is
the persisted, reproducible manifest the assessment asks for (debt §4) — a unit
can be re-validated from its state file alone, with the allowlist derived from
the ledger rather than hand-built.

Pure state model: it holds the ledger and delegates allowlist derivation to it.
It does not import the validators or run anything — see ``flow.runner`` for that,
so this module stays lightweight and side-effect-free except for its own I/O.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.flow.evidence_ledger import EvidenceLedger

# The unit journey (blueprint §3). Strictly ordered; regressions are allowed and
# recorded, never silent.
STAGES = ("OPEN", "GATHER", "DROP", "RUN", "REVIEW", "SHIP")

STATE_FILENAME = "state.yaml"
_VERSION_RE = re.compile(r"state\.v(\d+)\.yaml$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class UnitState:
    unit_name: str
    stage: str = "OPEN"
    version: int = 0                 # 0 = never saved; save() assigns 1, 2, ...
    manifest_snapshot: dict[str, Any] = field(default_factory=dict)
    checklist: list[dict[str, Any]] = field(default_factory=list)
    ledger: EvidenceLedger = field(default_factory=EvidenceLedger)
    gate_results: dict[str, Any] = field(default_factory=dict)
    verdicts: dict[str, Any] = field(default_factory=dict)
    # Landman-declared divergences, each with its recorded reason. Sheet-kind
    # entries feed the sheet-set rule (DECLARED EXCLUSION, not FAIL); anything
    # not declared here keeps the default FAIL.
    declared_exclusions: list[dict[str, str]] = field(default_factory=list)
    # Human sanctions of specific gate findings: key "Sheet!Cell:rule" ->
    # {reason, by, at, value}. Applied only while the finding's value is
    # unchanged — a changed cell voids its sanction.
    sanctions: dict[str, dict[str, str]] = field(default_factory=dict)
    packaging_summary: dict[str, Any] = field(default_factory=dict)
    unit_dpu_contract: str | None = None
    ddr_path: str | None = None
    stage_history: list[dict[str, str]] = field(default_factory=list)
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    # --- allowlist (delegated to the ledger; §3.1 fix) ---
    def derive_allowlist(self) -> dict[str, Any]:
        return self.ledger.derive_allowlist(self.unit_name)

    # --- stage transitions (ordered; regressions logged) ---
    def advance(self, to_stage: str, note: str = "") -> None:
        self._transition(to_stage, note, allow_regress=False)

    def regress(self, to_stage: str, reason: str) -> None:
        self._transition(to_stage, reason, allow_regress=True)

    def _transition(self, to_stage: str, note: str, allow_regress: bool) -> None:
        if to_stage not in STAGES:
            raise ValueError(f"unknown stage {to_stage!r}; expected one of {STAGES}")
        cur, nxt = STAGES.index(self.stage), STAGES.index(to_stage)
        if not allow_regress and nxt < cur:
            raise ValueError(
                f"cannot advance from {self.stage} back to {to_stage}; use regress()")
        self.stage_history.append(
            {"from": self.stage, "to": to_stage, "at": _now(), "note": note})
        self.stage = to_stage

    # --- persistence ---
    def to_dict(self) -> dict[str, Any]:
        return {
            "unit_name": self.unit_name, "stage": self.stage, "version": self.version,
            "manifest_snapshot": self.manifest_snapshot, "checklist": self.checklist,
            "ledger": self.ledger.to_dict(), "gate_results": self.gate_results,
            "verdicts": self.verdicts,
            "declared_exclusions": self.declared_exclusions,
            "sanctions": self.sanctions,
            "packaging_summary": self.packaging_summary,
            "unit_dpu_contract": self.unit_dpu_contract, "ddr_path": self.ddr_path,
            "stage_history": self.stage_history,
            "created_at": self.created_at, "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "UnitState":
        return cls(
            unit_name=d["unit_name"], stage=d.get("stage", "OPEN"),
            version=d.get("version", 0), manifest_snapshot=d.get("manifest_snapshot", {}),
            checklist=d.get("checklist", []),
            ledger=EvidenceLedger.from_dict(d.get("ledger")),
            gate_results=d.get("gate_results", {}), verdicts=d.get("verdicts", {}),
            declared_exclusions=d.get("declared_exclusions", []),
            sanctions=d.get("sanctions", {}),
            packaging_summary=d.get("packaging_summary", {}),
            unit_dpu_contract=d.get("unit_dpu_contract"), ddr_path=d.get("ddr_path"),
            stage_history=d.get("stage_history", []),
            created_at=d.get("created_at", _now()), updated_at=d.get("updated_at", _now()),
        )


# ---------------------------------------------------------------------------
# On-disk store
# ---------------------------------------------------------------------------

def state_dir(units_dir: str | Path, unit_name: str) -> Path:
    return Path(units_dir) / unit_name


def state_file(units_dir: str | Path, unit_name: str) -> Path:
    return state_dir(units_dir, unit_name) / STATE_FILENAME


def _next_version(directory: Path) -> int:
    versions = [int(m.group(1)) for p in directory.glob("state.v*.yaml")
                if (m := _VERSION_RE.search(p.name))]
    return (max(versions) + 1) if versions else 1


def save_state(state: UnitState, units_dir: str | Path) -> Path:
    """Persist the case file. Bumps the version and retains the prior snapshot:
    ``state.yaml`` (latest) plus ``state.v<N>.yaml`` (this version, retained).
    Returns the path to ``state.yaml``."""
    import yaml

    directory = state_dir(units_dir, state.unit_name)
    directory.mkdir(parents=True, exist_ok=True)
    state.version = _next_version(directory)
    state.updated_at = _now()
    data = state.to_dict()
    text = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
    latest = directory / STATE_FILENAME
    latest.write_text(text, encoding="utf-8")
    (directory / f"state.v{state.version}.yaml").write_text(text, encoding="utf-8")
    return latest


def load_state(unit_name: str, units_dir: str | Path) -> UnitState:
    """Load the latest case file for a unit. Raises if none exists."""
    import yaml

    path = state_file(units_dir, unit_name)
    if not path.exists():
        raise FileNotFoundError(f"no state file for {unit_name!r} at {path}")
    return UnitState.from_dict(yaml.safe_load(path.read_text(encoding="utf-8")))


def state_exists(unit_name: str, units_dir: str | Path) -> bool:
    return state_file(units_dir, unit_name).exists()
