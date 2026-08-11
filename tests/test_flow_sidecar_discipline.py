"""The sidecar must tell the truth, and a replay must not touch what shipped.

Two real defects found while reconciling Bowen:
- the sidecar was written INSIDE run_final_validation, before the flow layer
  applied the human rulings, so the file on disk announced "NOT READY — 2 FAIL"
  while the recorded verdict was READY / 0 FAIL;
- every regression replay rewrote that sidecar inside the DELIVERED package
  folder, mutating a shipped artefact as a side effect of re-validating it.
"""
from __future__ import annotations

from datetime import date

import openpyxl
import pytest

from src.dd.ddr_validator import run_final_validation


def _ddr(tmp_path):
    p = tmp_path / "DDR.xlsx"
    openpyxl.Workbook().save(p)
    return p


def _sidecar(ddr):
    return ddr.with_name(f"{ddr.stem}_validation.txt")


def test_a_replay_never_writes_a_sidecar(tmp_path):
    ddr = _ddr(tmp_path)
    run_final_validation(ddr, run_source_truth_check=False, as_of=date(2026, 7, 28))
    assert not _sidecar(ddr).exists()


def test_a_ship_time_run_does_write_its_sidecar(tmp_path):
    ddr = _ddr(tmp_path)
    run_final_validation(ddr, run_source_truth_check=False)
    assert _sidecar(ddr).exists()


def test_write_sidecar_false_defers_the_write_to_the_caller(tmp_path):
    # The flow runner uses this so the sidecar can be written after sanctions.
    ddr = _ddr(tmp_path)
    run_final_validation(ddr, run_source_truth_check=False, write_sidecar=False)
    assert not _sidecar(ddr).exists()


def test_the_runner_writes_the_sidecar_only_after_applying_rulings(tmp_path, monkeypatch):
    # A FAIL the human sanctioned must not appear as a FAIL in the file on disk.
    import src.flow.runner as runner
    from src.flow.evidence_ledger import EvidenceLedger
    from src.flow.unit_state import UnitState

    ddr = _ddr(tmp_path)
    st = UnitState(unit_name="U", ledger=EvidenceLedger(), ddr_path=str(ddr))
    captured = {}

    class _F:
        sheet, cell, rule, value, severity, expected = "S", "C1", "r", "v", "FAIL", "x"
        def describe(self):
            return "f"

    def fake_validation(*a, **kw):
        captured["write_sidecar"] = kw.get("write_sidecar")
        rep = type("R", (), {"findings": [_F()], "truth": None, "ready": True,
                             "failures": [], "pending": [], "coverage": [],
                             "summary": lambda self: "READY"})()
        return rep

    monkeypatch.setattr(runner, "run_final_validation", fake_validation, raising=False)
    monkeypatch.setattr("src.dd.ddr_validator.run_final_validation", fake_validation)
    st.sanctions = {"S!C1:r": {"reason": "ok", "by": "R", "value": "v"}}
    runner.revalidate_from_state(st, runner.Config(units_dir=str(tmp_path)),
                                 persist=False)
    assert captured["write_sidecar"] is False        # deferred, not written early
