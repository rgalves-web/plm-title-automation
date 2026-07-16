"""Derive a unit's contract set from the Lease-to-Well-and-Contract XREF
(Maxwell lessons item 2).

The XREF links each lease to every well and contract it touches. A unit's leases
therefore drag in contracts that have nothing to do with the unit: a lease
pooled into MAXWELL A may also be pooled into ALAMO A, so ALAMO's Declaration of
Pooled Unit appears against a Maxwell lease. Shipping those would tell the buyer
they are acquiring another unit's pooling.

The split, derived from the record type and the contract's own name:

  * chain-of-title contracts (assignment, farmout, partial assignment …) that
    touch any unit lease -> **Agreements**. These convey the leasehold and belong
    in the deliverable whether or not the PDF is in the file: when it is missing
    we still stub the row so the contract is visible and orderable.
  * the unit's OWN declaration of pooled unit -> **Unit and Pooling Agreements**.
  * a DPU naming a DIFFERENT unit -> excluded, with the reason recorded.

Nothing here guesses: a contract is this unit's DPU only when its name carries
the unit's distinctive name token(s).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

# Record types that pool land into a unit.
_UNIT_AGREEMENT_TYPES = {"UNIT AGREEMENT", "POOLING AGREEMENT", "UNIT DECLARATION"}

# The XREF's "WELL OR CONTRACT NB" column carries BOTH well numbers and contract
# numbers; these record types are not contracts at all and never reach Agreements.
_NON_CONTRACT_TYPES = {"WELL", "TITLE OPINIONS", "TITLE OPINION"}

# Tokens that carry no identity in a unit name: "MAXWELL A UNIT" is identified by
# MAXWELL, not by "A" or "UNIT".
_GENERIC_UNIT_TOKENS = {"UNIT", "THE", "A", "B", "C", "D", "AGREEMENT", "OF",
                        "POOLED", "DECL", "DECLARATION", "DEC"}

AGREEMENTS = "agreements"
UNIT_POOLING = "unit_pooling"
EXCLUDED = "excluded"

# Marker the writer stamps into a stub row when the contract PDF is absent.
PENDING_MARKER = "[PENDING - awaiting contract PDF]"


@dataclass
class UnitContract:
    contract_no: str
    name: str = ""
    record_type: str = ""
    leases: list[str] = field(default_factory=list)
    category: str = AGREEMENTS
    reason: str = ""
    document_path: Any | None = None   # set when the contract PDF is on disk

    @property
    def is_stub(self) -> bool:
        return self.document_path is None


def _tokens(text: str | None) -> set[str]:
    return {t for t in re.split(r"[^A-Z0-9]+", str(text or "").upper()) if t}


def unit_identity_tokens(unit_name: str | None) -> set[str]:
    """The distinctive tokens of a unit name — "MAXWELL A UNIT" -> {"MAXWELL"}."""
    return _tokens(unit_name) - _GENERIC_UNIT_TOKENS


def is_contract_row(record_type: str | None) -> bool:
    """False for the well and title-opinion rows that share the XREF's
    "WELL OR CONTRACT NB" column — they are not contracts."""
    return str(record_type or "").strip().upper() not in _NON_CONTRACT_TYPES


def classify_contract(record_type: str | None, contract_name: str | None,
                      unit_name: str | None) -> tuple[str, str]:
    """(category, reason) for one contract against the unit."""
    rtype = str(record_type or "").strip().upper()
    if rtype not in _UNIT_AGREEMENT_TYPES:
        # Everything else that touches a unit lease is chain of title. Note the
        # asymmetry of the risk: showing the reviewer a contract that turns out
        # to be irrelevant costs a glance; silently dropping one that conveys the
        # leasehold is a title defect in the deliverable. We surface it.
        return AGREEMENTS, f"chain-of-title contract ({rtype.title() or 'contract'})"

    identity = unit_identity_tokens(unit_name)
    name_tokens = _tokens(contract_name)
    if identity and identity & name_tokens:
        return UNIT_POOLING, "declaration of pooled unit for this unit"
    return EXCLUDED, (
        f"declaration of pooled unit for a DIFFERENT unit ({str(contract_name or '').strip()}) "
        "— shares a lease with this unit but does not pool this unit's land")


def build_unit_contracts(
    xref_rows: Iterable[dict[str, Any]],
    unit_name: str,
    unit_leases: Iterable[str],
) -> list[UnitContract]:
    """Group XREF rows into the unit's contract set, classified.

    xref_rows: dicts with keys lease_no, contract_no, contract_name, record_type.
    Only rows whose lease_no is one of the unit's leases are considered.
    """
    wanted = {str(x) for x in unit_leases}
    by_contract: dict[str, UnitContract] = {}
    for row in xref_rows:
        lease_no = str(row.get("lease_no") or "")
        contract_no = str(row.get("contract_no") or "").strip()
        if lease_no not in wanted or not contract_no:
            continue
        if not is_contract_row(row.get("record_type")):
            continue  # a well / title-opinion row, not a contract
        contract = by_contract.get(contract_no)
        if contract is None:
            category, reason = classify_contract(
                row.get("record_type"), row.get("contract_name"), unit_name)
            contract = UnitContract(
                contract_no=contract_no,
                name=str(row.get("contract_name") or "").strip(),
                record_type=str(row.get("record_type") or "").strip(),
                category=category,
                reason=reason,
            )
            by_contract[contract_no] = contract
        if lease_no not in contract.leases:
            contract.leases.append(lease_no)
    for contract in by_contract.values():
        contract.leases.sort()
    return [by_contract[k] for k in sorted(by_contract)]


def contracts_for(contracts: list[UnitContract], category: str) -> list[UnitContract]:
    return [c for c in contracts if c.category == category]


# ---------------------------------------------------------------------------
# XREF workbook reader (column names as printed in the client's XREF)
# ---------------------------------------------------------------------------

_CONTRACT_NB = "WELL OR CONTRACT NB"
_COLUMN_ALIASES = {
    "lease_no": ("LEASE NO",),
    "contract_no": (_CONTRACT_NB,),
    "contract_name": ("WELL OR CONTRACT NAME",),
}
# Sheets that are summaries, not lease/contract data.
_NON_DATA_SHEET = re.compile(r"pivot|summary|chart", re.IGNORECASE)


def resolve_columns(header: list[str]) -> dict[str, int]:
    """Map field -> column index, position-aware.

    The XREF repeats column NAMES for its two halves: the lease's own attributes
    come first, then the well/contract's. "RECORD TYPE" therefore appears twice —
    at index 5 it is the lease's type ("FEE- FREEHOLD"), at index 17 it is the
    contract's ("ASSIGNMENT", "UNIT AGREEMENT"). Taking the first match silently
    classifies every contract by its LEASE type. The contract's record type is
    the first "RECORD TYPE" appearing AFTER the contract-number column.
    """
    index: dict[str, int] = {}
    for key, aliases in _COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in header:
                index[key] = header.index(alias)
                break
    if "contract_no" in index:
        after = index["contract_no"]
        record_types = [i for i, h in enumerate(header) if h.upper().startswith("RECORD TYPE")]
        contract_types = [i for i in record_types if i > after]
        if contract_types:
            index["record_type"] = contract_types[0]
        elif record_types:  # older XREF exports disambiguated the name instead
            index["record_type"] = record_types[-1]
    missing = [k for k in (*_COLUMN_ALIASES, "record_type") if k not in index]
    if missing:
        raise ValueError(f"XREF is missing expected column(s) for {missing}; header={header}")
    return index


def read_xref_rows(path, sheet_name: str | None = None) -> list[dict[str, Any]]:
    """Read the XREF into lease/contract dicts. Contract rows only (a well row
    carries a well number, not a contract number).

    Reads EVERY data sheet unless one is named. The client's export splits its
    rows across Sheet1/Sheet2 with an identical header, and a unit's leases can
    straddle the split — Maxwell's State of Texas lease 0222854-000 lives only on
    Sheet2, so reading the first sheet alone silently drops it from the unit.
    """
    import openpyxl

    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        sheet_names = [sheet_name] if sheet_name else [
            s for s in workbook.sheetnames if not _NON_DATA_SHEET.search(s)]
        out: list[dict[str, Any]] = []
        for name in sheet_names:
            rows = workbook[name].iter_rows(values_only=True)
            try:
                header = [str(h).strip() if h is not None else "" for h in next(rows)]
            except StopIteration:
                continue
            index = resolve_columns(header)
            for row in rows:
                if not row:
                    continue
                record = {key: (str(row[pos]).strip() if row[pos] is not None else None)
                          for key, pos in index.items()}
                if record.get("lease_no") and record.get("contract_no"):
                    record["_sheet"] = name
                    out.append(record)
        return out
    finally:
        workbook.close()


def leases_for_unit_contract(xref_rows: Iterable[dict[str, Any]], contract_no: str) -> list[str]:
    """Every lease the XREF links to a contract — for a unit's own DPU, this is
    the unit's authoritative active lease list."""
    return sorted({str(r["lease_no"]) for r in xref_rows
                   if str(r.get("contract_no") or "").strip() == contract_no and r.get("lease_no")})
