"""Runner: the allowlist handed to the gate is DERIVED from the ledger, never typed."""
from __future__ import annotations

import pytest

from src.flow.config import Config
from src.flow.evidence_ledger import (
    KIND_CONTRACT,
    KIND_LEASE,
    KIND_TITLE_OPINION,
    EvidenceLedger,
)
from src.flow.runner import build_allowlist, revalidate_from_state
from src.flow.unit_state import UnitState


def _state() -> UnitState:
    led = EvidenceLedger()
    for t in ("T0140253", "T0140319", "T0140456"):
        led.record(f"{t}.pdf", KIND_TITLE_OPINION, t)
    led.record("K1400170.zip", KIND_CONTRACT, "K1400170")
    led.record("0190122-007.pdf", KIND_LEASE, "0190122-007")
    return UnitState(unit_name="MAXWELL A UNIT", ledger=led)


def test_build_allowlist_is_derived_from_the_ledger():
    allow = build_allowlist(_state())
    # It is the engine's real UnitAllowlist type, populated from confirmed evidence.
    from src.dd.ddr_validator import UnitAllowlist
    assert isinstance(allow, UnitAllowlist)
    assert allow.title_opinions == {"T0140253", "T0140319", "T0140456"}
    assert allow.contracts == {"K1400170"}
    assert allow.leases == {"0190122-007"}
    assert allow.identity_tokens == {"MAXWELL"}
    assert allow.unit_name == "MAXWELL A UNIT"


def test_unit_folder_walks_up_to_the_FILES_ancestor(tmp_path):
    # Bowen layout: the DDR sits nested in the submission tree; the unit root
    # (which holds FILES) is 3 levels up. Pointing the source index at the
    # DDR's parent yields 0 confirmed cells — an artifact, not a verdict.
    from src.flow.runner import _unit_folder
    unit = tmp_path / "BOWEN A UNIT"
    (unit / "FILES").mkdir(parents=True)
    ddr = unit / "Bowen A Unit" / "1. Landman Submitted" / "PLM Report" / "DDR.xlsx"
    ddr.parent.mkdir(parents=True)
    ddr.write_bytes(b"x")
    st = _state(); st.ddr_path = str(ddr)
    assert _unit_folder(st) == unit
    # Flat layout (Maxwell): DDR at the unit root, FILES beside it.
    flat = tmp_path / "MAXWELL A UNIT"
    (flat / "FILES").mkdir(parents=True)
    ddr2 = flat / "DDR.xlsx"; ddr2.write_bytes(b"x")
    st2 = _state(); st2.ddr_path = str(ddr2)
    assert _unit_folder(st2) == flat


def test_revalidate_requires_a_readable_ddr(tmp_path):
    st = _state()
    st.ddr_path = str(tmp_path / "does_not_exist.xlsx")
    with pytest.raises(FileNotFoundError):
        revalidate_from_state(st, Config(units_dir=str(tmp_path)), persist=False)
