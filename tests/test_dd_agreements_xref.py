"""Agreements completeness from the XREF (Maxwell lessons item 2).

Ground truth is the approved v5 baseline's Maxwell contract set. The XREF rows
below mirror the real client XREF's shape (record type + contract name), so the
classification is exercised exactly as it runs in production.
"""
from __future__ import annotations

import pytest

from src.dd.agreements_xref import (
    AGREEMENTS,
    EXCLUDED,
    UNIT_POOLING,
    build_unit_contracts,
    classify_contract,
    contracts_for,
    unit_identity_tokens,
)

_UNIT = "MAXWELL A UNIT"
_LEASES = ["0190122-001", "0190122-005", "0220344-013", "0220344-021", "0222854-000"]

# (contract_no, name, record_type) as the client's XREF prints them.
_XREF = [
    ("K1400049", "ASMT - JOE BOB SMITH", "ASSIGNMENT"),
    ("K1400170", "FARMOUT AGMT/ASMT - ENCANA TO EOG", "FARMOUT AGREEMENT"),
    ("K1400170-AAA", "PARTIAL ASMT-ENCANA(BURLINGTON) TO EOG", "ASSIGNMENT"),
    ("K1400347", " ASMT-JOE B SMITH TO EOG", "ASSIGNMENT"),
    ("K1400813", "DECL OF POOLED UNIT - MAXWELL UNIT A", "UNIT AGREEMENT"),
    # DPUs of OTHER units that merely share a lease — all out of scope.
    ("K1400235", "DECL OF POOLED UNIT - WIESE UNIT", "UNIT AGREEMENT"),
    ("K1400433", "SHERRILL UNIT #2H", "UNIT AGREEMENT"),
    ("K1400552", "DEC OF POOLED UNIT - SHERRILL A UNIT", "UNIT AGREEMENT"),
    ("K1400720", "DEC OF POOLED UNIT - IMA WILLIAMS UNIT", "UNIT AGREEMENT"),
    ("K1400721", "DEC OF POOLED UNIT - TOMPKINS UNIT", "UNIT AGREEMENT"),
    ("K1400818", "DECL OF POOLED UNIT - ALAMO A UNIT", "UNIT AGREEMENT"),
    ("K1401052", "DECL OF POOLED UNIT - ALAMO B UNIT", "UNIT AGREEMENT"),
    ("K1402471", "SADIE UNIT", "UNIT AGREEMENT"),
]


def _rows():
    return [{"lease_no": _LEASES[i % len(_LEASES)], "contract_no": no,
             "contract_name": name, "record_type": rtype}
            for i, (no, name, rtype) in enumerate(_XREF)]


def _built():
    return build_unit_contracts(_rows(), _UNIT, _LEASES)


def test_unit_identity_tokens_drop_generic_words():
    assert unit_identity_tokens("MAXWELL A UNIT") == {"MAXWELL"}


def test_maxwell_agreements_are_exactly_the_chain_of_title_contracts():
    got = {c.contract_no for c in contracts_for(_built(), AGREEMENTS)}
    assert got == {"K1400049", "K1400170", "K1400170-AAA", "K1400347"}


def test_maxwell_own_dpu_goes_to_unit_and_pooling():
    got = [c.contract_no for c in contracts_for(_built(), UNIT_POOLING)]
    assert got == ["K1400813"]


@pytest.mark.parametrize("contract_no", [
    "K1400235",   # Wiese
    "K1400433",   # Sherrill #2H
    "K1400552",   # Sherrill A
    "K1400720",   # Ima Williams
    "K1400721",   # Tompkins
    "K1400818",   # Alamo A
    "K1401052",   # Alamo B
    "K1402471",   # Sadie
])
def test_other_units_dpus_are_excluded(contract_no):
    excluded = {c.contract_no: c for c in contracts_for(_built(), EXCLUDED)}
    assert contract_no in excluded
    assert "DIFFERENT unit" in excluded[contract_no].reason


def test_every_contract_is_classified_exactly_once():
    contracts = _built()
    assert len(contracts) == len(_XREF)
    assert sum(len(contracts_for(contracts, c)) for c in (AGREEMENTS, UNIT_POOLING, EXCLUDED)) == len(_XREF)


def test_farmout_and_partial_assignment_are_chain_of_title():
    assert classify_contract("FARMOUT AGREEMENT", "FARMOUT AGMT/ASMT", _UNIT)[0] == AGREEMENTS
    assert classify_contract("ASSIGNMENT", "PARTIAL ASMT", _UNIT)[0] == AGREEMENTS


def test_contract_carries_the_leases_that_link_it():
    contract = next(c for c in _built() if c.contract_no == "K1400049")
    assert contract.leases == ["0190122-001"]


def test_contract_with_no_pdf_is_a_stub():
    assert all(c.is_stub for c in _built())  # no document_path resolved in this fixture


def test_well_and_title_opinion_rows_are_not_contracts():
    # The XREF's "WELL OR CONTRACT NB" column carries well numbers too; those
    # rows must never surface as chain-of-title agreements.
    rows = [{"lease_no": _LEASES[0], "contract_no": "14452-000",
             "contract_name": "SOME WELL 1H", "record_type": "WELL"},
            {"lease_no": _LEASES[0], "contract_no": "TO-123",
             "contract_name": "T-O ORIG COX", "record_type": "TITLE OPINIONS"}]
    assert build_unit_contracts(rows, _UNIT, _LEASES) == []


def test_real_xref_column_shape_keeps_only_k_contracts():
    rows = _rows() + [{"lease_no": _LEASES[0], "contract_no": "14563-000",
                       "contract_name": "WELL", "record_type": "WELL"}]
    assert all(c.contract_no.startswith("K") for c in build_unit_contracts(rows, _UNIT, _LEASES))


def test_rows_for_other_units_leases_are_ignored():
    rows = [{"lease_no": "9999999-999", "contract_no": "K9999999",
             "contract_name": "SOMETHING ELSE", "record_type": "ASSIGNMENT"}]
    assert build_unit_contracts(rows, _UNIT, _LEASES) == []


# --- real client XREF shape: duplicate headers + rows split across sheets ---

def test_contract_record_type_is_the_one_after_the_contract_number():
    # The XREF repeats column names: RECORD TYPE at 5 is the LEASE's type
    # ("FEE- FREEHOLD"), at 17 the CONTRACT's ("ASSIGNMENT"). Taking the first
    # match classifies every contract by its lease type.
    from src.dd.agreements_xref import resolve_columns
    header = ["INCLUDE FLAG", "LEASE NO", "LESSOR", "LESSEE", "ACTIVE FLAG",
              "RECORD TYPE", "RIGHTS HELD", "PROPERTY STATUS", "LEASE DATE",
              "EFF DATE", "EXP DATE", "EXT EXP DATE", "STATE", "COUNTY",
              "WELL OR CONTRACT NB", "WELL OR CONTRACT NAME", "ACTIVE FLAG",
              "RECORD TYPE", "RIGHTS HELD"]
    index = resolve_columns(header)
    assert index["record_type"] == 17, "must take the contract's record type, not the lease's"
    assert index["contract_no"] == 14 and index["lease_no"] == 1


def test_older_xref_disambiguated_header_still_resolves():
    from src.dd.agreements_xref import resolve_columns
    header = ["LEASE NO", "RECORD TYPE", "WELL OR CONTRACT NB",
              "WELL OR CONTRACT NAME", "RECORD TYPE3"]
    assert resolve_columns(header)["record_type"] == 4


def test_missing_columns_raise_rather_than_guess():
    from src.dd.agreements_xref import resolve_columns
    with pytest.raises(ValueError):
        resolve_columns(["LEASE NO", "SOMETHING ELSE"])


def test_leases_for_unit_contract_collects_across_sheets():
    from src.dd.agreements_xref import leases_for_unit_contract
    rows = [{"lease_no": "0190122-001", "contract_no": "K1400813", "_sheet": "Sheet1"},
            {"lease_no": "0222854-000", "contract_no": "K1400813", "_sheet": "Sheet2"},
            {"lease_no": "9999999-999", "contract_no": "K1400235", "_sheet": "Sheet1"}]
    # Maxwell's State of Texas lease lives only on Sheet2 — reading one sheet drops it.
    assert leases_for_unit_contract(rows, "K1400813") == ["0190122-001", "0222854-000"]
