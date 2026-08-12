"""Unit state: the versioned, reproducible case file the assessment asks for."""
from __future__ import annotations

import pytest

from src.flow.evidence_ledger import KIND_TITLE_OPINION, EvidenceLedger
from src.flow.unit_state import (
    UnitState,
    load_state,
    save_state,
    state_exists,
    state_file,
)


def _state() -> UnitState:
    led = EvidenceLedger()
    led.record("T-O.PDF", KIND_TITLE_OPINION, "T0140253")
    return UnitState(unit_name="MAXWELL A UNIT", ledger=led,
                     manifest_snapshot={"client_name": "BKV"}, ddr_path="X.xlsx")


def test_save_load_roundtrip(tmp_path):
    st = _state()
    save_state(st, tmp_path)
    assert state_exists("MAXWELL A UNIT", tmp_path)
    back = load_state("MAXWELL A UNIT", tmp_path)
    assert back.unit_name == "MAXWELL A UNIT"
    assert back.manifest_snapshot["client_name"] == "BKV"
    assert back.derive_allowlist()["title_opinions"] == {"T0140253"}


def test_versioning_retains_prior_snapshots(tmp_path):
    st = _state()
    save_state(st, tmp_path)                 # v1
    assert st.version == 1
    save_state(st, tmp_path)                 # v2
    assert st.version == 2
    d = tmp_path / "MAXWELL A UNIT"
    assert (d / "state.yaml").exists()
    # Snapshots live under versions/ — twenty-six state.v*.yaml beside the
    # current one is how a unit folder stops being readable (PR-9 item 0).
    assert (d / "versions" / "state.v1.yaml").exists()
    assert (d / "versions" / "state.v2.yaml").exists()
    assert not (d / "state.v1.yaml").exists()


def test_numbering_survives_the_migration_of_old_snapshots(tmp_path):
    # Old rounds left snapshots in the unit root; the migration moved them to
    # versions/. The next save must continue the count, not restart it.
    st = _state()
    d = tmp_path / "MAXWELL A UNIT"
    (d / "versions").mkdir(parents=True)
    (d / "versions" / "state.v7.yaml").write_text("legacy", encoding="utf-8")
    save_state(st, tmp_path)
    assert st.version == 8


def test_derive_allowlist_delegates_to_ledger(tmp_path):
    st = _state()
    assert st.derive_allowlist()["identity_tokens"] == {"MAXWELL"}


def test_stage_advance_and_regress_are_ordered_and_logged():
    st = _state()
    st.advance("GATHER")
    st.advance("DROP")
    assert st.stage == "DROP"
    with pytest.raises(ValueError):
        st.advance("OPEN")                   # cannot advance backwards
    st.regress("GATHER", reason="new evidence arrived")
    assert st.stage == "GATHER"
    assert st.stage_history[-1]["note"] == "new evidence arrived"


def test_load_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_state("NO SUCH UNIT", tmp_path)


def test_state_file_path(tmp_path):
    assert state_file(tmp_path, "U").name == "state.yaml"
