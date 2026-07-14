"""Due Diligence unit manifest — pydantic schema.

A UnitManifest captures everything build_manifest() can derive deterministically
from the 3 client reference workbooks for one acquisition unit (e.g. "BOWEN A
UNIT"): its title opinions, reference contracts, leases, wells, and the
Well List's represented WI/NRI baseline. Fraction-bearing fields are stored as
strings end to end so Fraction(value) round-trips exactly in unit_aggregation.py
(Fraction(float(value)) would introduce binary-float artifacts).

confirm_coverage is a deterministic, spreadsheet-derived flag set once by
manifest_builder and never overwritten afterward. predicted_unit_coverage is a
separate, LLM-sourced, advisory-only field populated later by
title_opinion_parser — it never clears confirm_coverage; that requires an
explicit human action.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from src.llm_extractor import LLMFieldResult


class TitleOpinionRef(BaseModel):
    file_number: str
    record_type: str = "TITLE OPINIONS"
    lessor: str | None = None
    lease_no: str | None = None
    match_method: str | None = None
    matched_unit_tokens: list[str] = Field(default_factory=list)
    confirm_coverage: bool = True
    pdf_available: bool = False
    pdf_path: str | None = None
    # Analyst-assigned tract-chain label (e.g. "COX", "KRAMER", "BRUMBAUGH").
    # Opinions sharing a label form one Original -> Supplement chain over the
    # same tract; select_ownership_basis picks the newest parseable opinion
    # PER CHAIN and aggregates across chains. None = ungrouped (single-chain
    # units keep the pre-existing newest-opinion-wins behavior).
    tract_chain: str | None = None
    predicted_unit_coverage: LLMFieldResult | None = None
    parse_result_path: str | None = None
    source_rows: list[int] = Field(default_factory=list)


class ReferenceContractRef(BaseModel):
    file_number: str
    record_type: str
    lessor: str | None = None
    lessee: str | None = None
    lease_no: str | None = None
    # Enrichment fields for the Unit and Pooling Agreements card (the XREF
    # carries none of these; they come from reading the recorded instrument,
    # e.g. the DPU itself) — analyst-supplied, optional.
    recording_info: str | None = None
    effective_date: str | None = None
    unit_description: str | None = None
    formations: str | None = None
    notes: str | None = None
    matched_unit_tokens: list[str] = Field(default_factory=list)
    source_rows: list[int] = Field(default_factory=list)


class LeaseRef(BaseModel):
    lease_no: str
    lessor: str | None = None
    lessee: str | None = None
    lease_date: date | None = None
    eff_date: date | None = None
    exp_date: date | None = None
    ext_exp_date: date | None = None
    property_status: str | None = None
    rights_held: str | None = None
    state: str | None = None
    county: str | None = None
    matched_unit_tokens: list[str] = Field(default_factory=list)
    source_rows: list[int] = Field(default_factory=list)


class WellRef(BaseModel):
    well_name: str
    well_operator: str | None = None
    well_api: str | None = None
    well_prod_status: str | None = None
    current_wi: str
    current_nri: str
    unit_name_raw: str | None = None


class RepresentedInterest(BaseModel):
    """The Well List's stated WI/NRI — the reconciliation target in unit_aggregation.py.

    basis distinguishes WHAT KIND of interest the figure is. The Well List's
    numbers are WELLBORE interests (they include non-consent/JOA uplift earned
    by operating), while title aggregation computes a LEASEHOLD interest —
    two different quantities that must never be delta-compared as if a gap
    between them were a title defect. Reconciliation only runs like-for-like:
    basis="leasehold" figures reconcile against the computed aggregate;
    basis="wellbore" figures are displayed side by side with status N/A.
    """

    current_wi: str
    current_nri: str
    basis: str = "wellbore"
    source: str = "Well List with Prelim AV% directional estimates.xlsx"
    as_of_well_names: list[str] = Field(default_factory=list)


class UnitManifest(BaseModel):
    unit_name: str
    operator: str | None = None
    county: str | None = None
    state: str = "Texas"
    seller_name: str | None = None
    # Run-level report metadata written to the DDR Summary tab. client_name
    # falls back to seller_name and acquisition_name to unit_name when unset,
    # so pre-existing callers keep their output unchanged.
    client_name: str | None = None
    acquisition_name: str | None = None
    landman_name: str | None = None
    date_submitted: str | None = None
    dsu_description: str | None = None
    aov_percent: float | None = None
    scope_of_review: str | None = None
    wells: list[WellRef] = Field(default_factory=list)
    title_opinions: list[TitleOpinionRef] = Field(default_factory=list)
    reference_contracts: list[ReferenceContractRef] = Field(default_factory=list)
    leases: list[LeaseRef] = Field(default_factory=list)
    represented_interest: RepresentedInterest | None = None
    unit_gross_acres: str | None = None
    # Expected Seller aggregate leasehold WI for the reconciliation gate
    # (config/analyst-supplied per unit, e.g. "0.816596" for MAXWELL A UNIT).
    # None disables the gate. Never hardcoded in code.
    expected_seller_wi: str | None = None
    controlling_certification_date: date | None = None
    has_farmout_option_scenario: bool = False
    manifest_notes: list[str] = Field(default_factory=list)
    generated_at: str = ""
    source_workbooks: dict[str, str] = Field(default_factory=dict)
