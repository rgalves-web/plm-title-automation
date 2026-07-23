"""Due Diligence pipeline orchestration for one acquisition unit.

Two-step engagement scope (PLM landman instructions): (1) identify the title
opinions covering the unit's leases — manifest_builder.py — and (2) run
supplemental title from each controlling title opinion's certification date
to present day, limited to the interest of the Seller (e.g. EOG).

This module owns step (2)'s scope filter plus the end-to-end orchestration
that wires manifest_builder -> title_opinion_parser -> unit_aggregation ->
ddr_writer together. It reuses MOR's classify/dedupe/QA machinery for the
supplemental document list rather than building a parallel engine.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from fractions import Fraction
from pathlib import Path
from typing import Any, Callable

ProgressCallback = Callable[[str, str], None]


def _emit(callback: ProgressCallback | None, icon: str, message: str) -> None:
    if callback:
        callback(icon, message)

from rapidfuzz import fuzz

from src.classifier import classify_documents
from src.dd.ddr_writer import DDRWriteResult, fill_ddr_template
from src.dd.manifest import UnitManifest
from src.dd.manifest_builder import build_and_write_manifest, set_title_opinions_from_uploads, write_manifest
from src.dd.title_opinion_parser import TitleOpinionExtraction, TOLeaseBlock, parse_title_opinion
from src.dd.unit_aggregation import (
    AggregationError,
    LeaseTractRow,
    derive_wi_from_nri_formula,
    parse_fraction_text,
    run_dd_aggregation,
)
from src.dedupe import deduplicate_documents
from src.ownership import canonical_party_key
from src.pdf_reader import _parse_extracted_date
from src.qa import run_qa
from src.schemas import ClassificationStatus, ProjectMetadata, QAException, SourceDocument
from src.utils import get_logger, write_json

logger = get_logger(__name__)

DD_NO_CONTROLLING_CERTIFICATION_DATE = "DD_NO_CONTROLLING_CERTIFICATION_DATE"
PREDATES_CERTIFICATION_REASON = "Instrument predates controlling title opinion certification date."
OUTSIDE_SELLER_INTEREST_REASON = "Instrument does not affect Seller's interest."
SELLER_PARTY_MATCH_THRESHOLD = 80


class SupplementalScopeError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Step 2: controlling certification date + supplemental scope filter
# ---------------------------------------------------------------------------

def resolve_controlling_certification_date(
    manifest: UnitManifest,
    to_extractions: dict[str, TitleOpinionExtraction],
) -> date:
    """Latest certification date among confirm_coverage=True title opinions
    that were successfully parsed. Raises SupplementalScopeError if none
    resolve — this is a hard stop, never a guess."""
    candidate_dates: list[date] = []
    for to_ref in manifest.title_opinions:
        if not to_ref.confirm_coverage:
            continue
        extraction = to_extractions.get(to_ref.file_number)
        if not extraction or extraction.error:
            continue
        for tract in extraction.tracts:
            cert_value = tract.certification_date.value if tract.certification_date else None
            if not cert_value:
                continue
            parsed = _parse_extracted_date(str(cert_value))
            if parsed:
                candidate_dates.append(parsed)

    if not candidate_dates:
        raise SupplementalScopeError(
            f"No controlling certification date could be resolved for unit "
            f"'{manifest.unit_name}' - no confirmed title opinion (confirm_coverage=True) "
            "has a successfully parsed certification date."
        )
    return max(candidate_dates)


def controlling_certification_date_qa_exception(
    manifest: UnitManifest, error: Exception
) -> QAException:
    return QAException(
        severity="ERROR",
        code=DD_NO_CONTROLLING_CERTIFICATION_DATE,
        message=str(error),
        field="controlling_certification_date",
    )


def _touches_seller_interest(record: SourceDocument, seller_key: str) -> bool:
    for party in (record.grantor, record.grantee):
        if not party:
            continue
        party_key = canonical_party_key(party)
        if not party_key:
            continue
        if seller_key in party_key or party_key in seller_key:
            return True
        if fuzz.token_sort_ratio(seller_key, party_key) >= SELLER_PARTY_MATCH_THRESHOLD:
            return True
    return False


def apply_supplemental_scope_filter(
    records: list[SourceDocument],
    controlling_certification_date: date,
    seller_name: str | None,
) -> None:
    """Mutates records in place: limits the supplemental document list to
    instruments recorded after the controlling certification date AND
    affecting the Seller's interest. Records failing either check are marked
    REDLINE with an explicit redline_reason — never silently dropped.

    certification_date is written to both source_trace and the typed field
    on every record processed, in- or out-of-scope, per the audit trail
    requirement.
    """
    seller_key = canonical_party_key(seller_name) if seller_name else ""

    for record in records:
        record.certification_date = controlling_certification_date
        record.source_trace["certification_date"] = controlling_certification_date.isoformat()

        if record.status in (ClassificationStatus.REDLINE, ClassificationStatus.DUPLICATE):
            continue

        instrument_date = record.recording_date or record.effective_date
        if instrument_date is None or instrument_date <= controlling_certification_date:
            record.status = ClassificationStatus.REDLINE
            record.redline_reason = PREDATES_CERTIFICATION_REASON
            continue

        if seller_key and not _touches_seller_interest(record, seller_key):
            record.status = ClassificationStatus.REDLINE
            record.redline_reason = OUTSIDE_SELLER_INTEREST_REASON


# ---------------------------------------------------------------------------
# Glue: manifest + TO extractions -> ddr_writer inputs
# ---------------------------------------------------------------------------

def _match_lease_block(
    lessor: str | None,
    all_lease_blocks: list[tuple[str, "TOTract", TOLeaseBlock]],
) -> tuple[str, "TOTract", TOLeaseBlock] | None:
    if not lessor:
        return None
    lessor_key = canonical_party_key(lessor)
    best: tuple[str, "TOTract", TOLeaseBlock] | None = None
    best_score = 0.0
    for file_number, tract, block in all_lease_blocks:
        block_lessor = block.lessor.value if block.lessor else None
        if not block_lessor:
            continue
        score = fuzz.token_sort_ratio(lessor_key, canonical_party_key(str(block_lessor)))
        if score > best_score and score >= SELLER_PARTY_MATCH_THRESHOLD:
            best_score = score
            best = (file_number, tract, block)
    return best


def build_lease_review_rows(
    manifest: UnitManifest,
    to_extractions: dict[str, TitleOpinionExtraction],
) -> list[dict[str, Any]]:
    all_lease_blocks: list[tuple[str, Any, TOLeaseBlock]] = []
    for to_ref in manifest.title_opinions:
        extraction = to_extractions.get(to_ref.file_number)
        if not extraction or extraction.error:
            continue
        for tract in extraction.tracts:
            for block in tract.leases:
                all_lease_blocks.append((to_ref.file_number, tract, block))

    rows: list[dict[str, Any]] = []
    for lease in manifest.leases:
        row: dict[str, Any] = {
            "lease_no": lease.lease_no,
            "lease_type": "Fee",
            "lessor": lease.lessor,
            "lessee": lease.lessee,
        }
        match = _match_lease_block(lease.lessor, all_lease_blocks)
        if match:
            file_number, tract, block = match
            row.update(
                {
                    "effective_date": block.lease_date.value,
                    "recording_info": block.recording_info.value,
                    "legal_description": block.land_covered.value,
                    "primary_term": block.primary_term.value,
                    "royalty_text": block.royalty.value,
                    "shut_in_royalty": block.shut_in_royalty.value,
                    "depth_limitations": block.depth_limitations.value,
                    "horizontal_pugh": block.pugh_clause.value,
                    "vertical_pugh": block.pugh_clause.value,
                    "confidence": min(
                        (
                            f.confidence
                            for f in (block.lease_date, block.recording_info, block.lessor, block.lessee)
                        ),
                        default=0.0,
                    ),
                    "source_to_file_number": file_number,
                }
            )
            # MI and WI are intentionally NOT set here. Matching a lease *block*
            # says nothing about which of a tract's several mineral owners this
            # lessor is, so taking mineral_owners[0] (or the tract-aggregate WI)
            # would flatten every lease in a multi-owner tract to one owner's
            # fraction. Per-lease MI/WI come from enrich_lease_rows_with_details,
            # which name-matches each lessor to its OWN mineral owner (the
            # authoritative per-owner fraction). Only royalty/ORRI — which are
            # genuinely tract-level here — are pulled from the matched tract.
            # Royalty: parse the first royalty_owner fraction; fall back to
            # block.royalty text (which is prose like "1/8 for oil").
            royalty = None
            if tract.royalty_owners:
                royalty = parse_fraction_text(tract.royalty_owners[0].fraction_text)
                if royalty is not None:
                    row["royalty"] = royalty
            if royalty is None and block.royalty.value:
                royalty = parse_fraction_text(block.royalty.value)
                if royalty is not None:
                    row["royalty"] = royalty
            # ORRI: sum all overriding royalty owner fractions that parse cleanly.
            orri_total = None
            for orri_owner in tract.overriding_royalty_owners:
                orri = parse_fraction_text(orri_owner.fraction_text)
                if orri is not None:
                    orri_total = (orri_total or 0) + orri
            if orri_total is not None:
                row["orri_burdens"] = orri_total
        rows.append(row)
    return rows


def enrich_lease_rows_with_details(
    lease_review_rows: list[dict[str, Any]],
    manifest: UnitManifest,
    controlling: dict[str, TitleOpinionExtraction],
    reconciliation: "ReconciliationResult",
    lease_document_details: dict[str, dict[str, Any]] | None = None,
) -> tuple[list[Any], list[str]]:
    """Fill per-lease MI/WI/royalty/tract-acres/legal on each row from the
    controlling opinions' mineral ownership (Collin items 1-2), never
    overwriting a value already resolved from a matched lease block. Returns the
    QA gate results (MI-sums-to-1 per tract, Seller WI == expected)."""
    from src.dd.lease_detail import build_lease_details
    from src.dd.dd_qa_gates import (
        mineral_interest_sums_to_one,
        mineral_interest_within_tract_not_over_one,
        seller_wi_matches_expected,
        workbook_headline_wi,
    )

    royalty_by_lease = {
        r["lease_no"]: (r.get("royalty_text") or r.get("royalty"))
        for r in lease_review_rows
        if r.get("lease_no") and (r.get("royalty_text") or r.get("royalty"))
    }
    details = {
        d.lease_no: d
        for d in build_lease_details(
            manifest.leases, controlling, royalty_by_lease,
            tract_gross_fn=_tract_gross_acres,
            # The Seller's WI as the CONTROLLING opinion states it. `controlling`
            # already holds the newest opinion per chain, so a supplement's
            # figure supersedes the original's (Cox SUPP .84953704, not ORIG
            # .82175926; Brumbaugh SUPP .625).
            tract_wi_fn=lambda t: resolve_seller_wi(t)[0],
        )
    }
    for row in lease_review_rows:
        d = details.get(row.get("lease_no"))
        if d is None:
            continue
        # Name-matched per-owner MI is authoritative and ALWAYS wins — it must
        # never be left flattened to a tract-uniform value. The lease-block
        # interest_covered is only a fallback: it fills an empty MI, but never
        # overwrites an owner match.
        if d.mi_value is not None:
            if d.mi_source == "mineral_owner" or row.get("mi_value") is None:
                row["mi_value"] = d.mi_value
        # WI is the controlling opinion's stated tract figure and always wins:
        # it is sourced, not inferred, so nothing earlier in the pipeline should
        # override it. An unstated WI carries its reason instead of a value.
        if d.wi_value is not None:
            row["wi_value"] = d.wi_value
            row["wi_source"] = d.wi_source
        elif d.wi_reason:
            row["wi_reason"] = d.wi_reason
        if d.mi_reason and d.mi_value is None:
            row["mi_reason"] = d.mi_reason
        if row.get("tract_gross_acres") is None and d.tract_gross_acres is not None:
            row["tract_gross_acres"] = d.tract_gross_acres
        if not row.get("legal_description") and d.legal_description:
            row["legal_description"] = d.legal_description
        # Royalty into the Ownership Report (col G): prefer a carried Lease
        # Review value, then the matched tract royalty. Parse the leading
        # fraction/percent from prose like "20% on oil, gas and casinghead gas".
        if row.get("royalty") is None and d.royalty is not None:
            from src.dd.lease_detail import _leading_fraction
            parsed = _leading_fraction(d.royalty)
            if parsed is not None:
                row["royalty"] = parsed
        if d.tract_key and not row.get("tract_key"):
            row["tract_key"] = d.tract_key
        if not row.get("source_to_file_number") and d.source:
            row["source_lease_detail"] = d.source
        if d.notes:
            row.setdefault("notes", []).extend(d.notes)

    # Merge the authoritative recorded-lease-document fields. Fill empties; on a
    # genuine TO-vs-document disagreement, itemize the conflict (never silent) —
    # the recorded instrument wins for lease terms, but both values are reported.
    conflicts = _merge_lease_document_details(lease_review_rows, lease_document_details or {})

    computed_wi = reconciliation.computed_wi if reconciliation and reconciliation.wi_status not in ("NOT_COMPUTED",) else None
    unit_gross = parse_fraction_text(str(manifest.unit_gross_acres)) if manifest.unit_gross_acres else None
    gate_results = [
        mineral_interest_sums_to_one(controlling),
        mineral_interest_within_tract_not_over_one(lease_review_rows),
        seller_wi_matches_expected(computed_wi, manifest.expected_seller_wi),
        workbook_headline_wi(lease_review_rows, unit_gross, manifest.expected_seller_wi),
    ]
    return gate_results, conflicts


def _documents_on_disk(unit_folder) -> set[str]:
    """Contract/lease identifiers whose packages exist in the unit folder."""
    if unit_folder is None:
        return set()
    from src.dd.ddr_validator import documents_on_disk
    return documents_on_disk(unit_folder)


def _validation_allowlist(manifest: UnitManifest, lease_review_rows: list[dict[str, Any]]):
    """What legitimately belongs to THIS unit, for the leakage rules."""
    from src.dd.agreements_xref import unit_identity_tokens
    from src.dd.ddr_validator import UnitAllowlist

    return UnitAllowlist(
        unit_name=manifest.unit_name,
        leases={str(r.get("lease_no")) for r in lease_review_rows if r.get("lease_no")}
               | {str(x.lease_no) for x in manifest.leases if getattr(x, "lease_no", None)},
        contracts={str(c.file_number) for c in manifest.reference_contracts
                   if getattr(c, "file_number", None)},
        title_opinions={str(t.file_number) for t in manifest.title_opinions
                        if getattr(t, "file_number", None)},
        identity_tokens=set(unit_identity_tokens(manifest.unit_name)),
    )


def _build_provenance_store(lease_review_rows, controlling, to_files_dir,
                            unit_folder, lease_document_dir, dpu_recording_map):
    """Locate document+page for each derived value, INDEPENDENTLY of the
    extraction. Returns a ProvenanceStore (internal; rides in the sidecar and
    audit trail, never a tab)."""
    from src.dd.provenance import populate_provenance
    from src.dd.source_truth_check import SourceIndex

    roots = [Path(p) for p in (unit_folder, to_files_dir, lease_document_dir,
                               Path("data/working/maxwell_a_unit_tos")) if p]
    try:
        index = SourceIndex(roots)
    except Exception as exc:  # provenance is best-effort; never blocks a write
        logger.warning("Provenance index unavailable: %s", exc)
        return None
    # Controlling opinion OCR: the documents MI/WI values must be found in.
    controlling_docs = []
    for file_number in controlling:
        path = index.resolve(file_number)
        if path is not None:
            try:
                controlling_docs.append((path.name, index.text(path)))
            except Exception:  # noqa: BLE001 — a single unreadable doc must not stop the rest
                continue
    # The writer lays rows out from Excel row 8 in list order; mirror that so the
    # provenance cells line up with the cells the writer actually wrote.
    for i, row in enumerate(lease_review_rows):
        row["_excel_row"] = 8 + i
    store, notes = populate_provenance(
        lease_review_rows, index, controlling_docs=controlling_docs,
        dpu_recording_map=dpu_recording_map)
    for note in notes:
        logger.info("Provenance: %s", note)
    return store


def _validation_source_roots(unit_folder, to_files_dir, lease_document_dir) -> list[Path]:
    """Where source-truth looks for the documents the audit trail cites."""
    return [Path(p) for p in (unit_folder, to_files_dir, lease_document_dir) if p]


def _register_pending_reasons(rows: list[dict[str, Any]], registry) -> None:
    """Turn each row's per-field reason into a Pending Items entry.

    The reason never goes into the client cell — it goes here, so a blank in the
    workbook can always be traced to why it is blank and what to do about it.
    """
    from src.dd.dd_pending import PendingReason

    fields = (
        ("mi_value", "mi_reason", "MI Value (col S)",
         "the controlling opinion's MINERALS section for this lessor"),
        ("wi_value", "wi_reason", "WI Value (col T)",
         "the controlling opinion's LEASEHOLD ESTATE table for this tract"),
        ("tract_gross_acres", None, "Tract Gross Acres (col R)",
         "the controlling opinion's tract description"),
    )
    for row in rows:
        lease_no = str(row.get("lease_no") or "?")
        for value_key, reason_key, label, where in fields:
            if row.get(value_key) is not None:
                continue
            reason = row.get(reason_key) if reason_key else None
            if reason is None:
                reason = PendingReason.NOT_FOUND
            registry.add("Ownership Report", f"row {lease_no}", label, reason, where,
                         identifier=f"lease {lease_no}")


def _merge_lease_document_details(
    lease_review_rows: list[dict[str, Any]],
    lease_document_details: dict[str, dict[str, Any]],
) -> list[str]:
    conflicts: list[str] = []
    rows_by_lease = {r.get("lease_no"): r for r in lease_review_rows}
    for lease_no, fields in lease_document_details.items():
        row = rows_by_lease.get(lease_no)
        if row is None:
            continue
        source = fields.get("_source", "lease document")
        for key, value in fields.items():
            if key.startswith("_"):
                continue
            existing = row.get(key)
            if existing in (None, "", "-"):
                row[key] = value
            elif _values_conflict(existing, value):
                conflicts.append(
                    f"{lease_no} · {key}: title opinion says {str(existing)[:50]!r}; "
                    f"{source} says {str(value)[:50]!r} — using the recorded instrument; verify.")
                row[key] = value
        # Ownership Report royalty (col G) is a Fraction parsed from the text.
        if row.get("royalty") is None and row.get("royalty_text"):
            from src.dd.lease_detail import _leading_fraction
            frac = _leading_fraction(row["royalty_text"])
            if frac is not None:
                row["royalty"] = frac
        row["source_lease_document"] = source
    return conflicts


def _normalize_for_conflict(text: Any) -> str:
    s = str(text).lower()
    s = re.sub(r"\bvolume\b", "vol", s)
    s = re.sub(r"\bpage\b", "pg", s)
    s = re.sub(r"[^a-z0-9 ]+", " ", s)  # drop punctuation
    return re.sub(r"\s+", " ", s).strip()


def _values_conflict(a: Any, b: Any) -> bool:
    """True only for a meaningful disagreement — normalize case / punctuation /
    common abbreviations and ignore a pure substring/superset (a title-opinion
    summary vs the fuller recorded-instrument text)."""
    sa, sb = _normalize_for_conflict(a), _normalize_for_conflict(b)
    if not sa or not sb or sa == sb:
        return False
    return sa not in sb and sb not in sa


def build_to_summaries(
    manifest: UnitManifest,
    to_extractions: dict[str, TitleOpinionExtraction],
) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for to_ref in manifest.title_opinions:
        extraction = to_extractions.get(to_ref.file_number)
        if not extraction or extraction.error or not extraction.tracts:
            summaries.append(
                {
                    "file_number": to_ref.file_number,
                    "type_description": "Title Opinion (no PDF available)" if not to_ref.pdf_available else "Title Opinion (parse error)",
                    "certification_date": None,
                    "legal_description": None,
                    "requirements": "PDF not yet available for review." if not to_ref.pdf_available else "Parse error — needs manual review.",
                    "confidence": 0.0,
                }
            )
            continue
        tract = extraction.tracts[0]
        requirements = "; ".join(r.value for r in tract.requirements if r.value) or "-"
        confidences = [
            f.confidence
            for f in (tract.certification_date, tract.tract_legal_description)
            if f
        ]
        summaries.append(
            {
                "file_number": to_ref.file_number,
                "type_description": _to_type_description(to_ref.file_number),
                "certification_date": tract.certification_date.value,
                "legal_description": tract.tract_legal_description.value,
                "requirements": requirements,
                "confidence": min(confidences) if confidences else 0.0,
            }
        )
    return summaries


def _to_type_description(file_number: str) -> str:
    """Human-readable opinion type from the client's own filename convention
    (file numbers built from descriptive stems carry ORIG / SUPP / SECOND SUPP
    / REVISED markers)."""
    upper = file_number.upper()
    if "SECOND" in upper and "SUPP" in upper:
        return "Second Supplemental Title Opinion"
    if "SUPP" in upper:
        return "Supplemental Title Opinion"
    if "REVISED" in upper:
        return "Revised Original Title Opinion"
    return "Original Title Opinion"


# "140.9963 acres", "22 1/3 acres" (mixed number), "1,234.5 acres". The
# lookbehind stops a match from starting mid-number (e.g. the "3" of "1/3").
_ACRES_RE = re.compile(
    r"(?<![\d/.])(\d{1,3}(?:,\d{3})*(?:\.\d+)?)"
    r"(?:\s+(\d{1,2})\s*/\s*(\d{1,2}))?"
    r"\s*ac(?:re)?s?\b",
    re.IGNORECASE,
)


def _tract_gross_acres(tract: Any) -> Fraction | None:
    """The tract's gross surface acreage as an exact Fraction. Prefers the
    LLM-extracted `tract_gross_acres` field; falls back to the first "NNN acres"
    figure (mixed numbers like "22 1/3 acres" included) in the legal
    description text so pre-existing extractions (or ones where the model left
    the dedicated field null) still resolve."""
    field = getattr(tract, "tract_gross_acres", None)
    if field and field.value:
        value = parse_fraction_text(str(field.value).replace(",", ""))
        if value is not None and value > 0:
            return value
    legal = getattr(tract, "tract_legal_description", None)
    if legal and legal.value:
        match = _ACRES_RE.search(str(legal.value))
        if match:
            value = parse_fraction_text(match.group(1).replace(",", ""))
            if value is not None and value > 0:
                if match.group(2) and match.group(3) and int(match.group(3)) != 0:
                    value += Fraction(int(match.group(2)), int(match.group(3)))
                return value
    return None


def _opinion_cert_date(extraction: TitleOpinionExtraction) -> date | None:
    """The opinion's own certification date = the latest parseable tract
    certification date within it."""
    latest: date | None = None
    for tract in extraction.tracts:
        cert = tract.certification_date.value if tract.certification_date else None
        parsed = _parse_extracted_date(str(cert)) if cert else None
        if parsed and (latest is None or parsed > latest):
            latest = parsed
    return latest


def _opinion_letter_date(extraction: TitleOpinionExtraction) -> date | None:
    """Latest parseable letter date — the tie-breaker when a supplement is
    'certified through' the same date as the original it revises (common:
    the supplement re-certifies the same effective date months later)."""
    latest: date | None = None
    for tract in extraction.tracts:
        raw = tract.letter_date.value if tract.letter_date else None
        parsed = _parse_extracted_date(str(raw)) if raw else None
        if parsed and (latest is None or parsed > latest):
            latest = parsed
    return latest


def _dedupe_tracts(tracts: list[Any]) -> list[Any]:
    """Collapse tracts that describe the same physical land. A long supplement
    is often over-segmented by the parser into several tracts that share the
    same acreage and legal description (e.g. the Second Supplement yielding
    three copies of the one 119.2-acre tract). Keyed on gross acres + the head
    of the legal description; among duplicates the most complete one wins (has a
    Seller working interest, then most mineral owners)."""
    def completeness(tract: Any) -> tuple[int, int]:
        return (1 if tract.seller_working_interest else 0, len(tract.mineral_owners))

    best: dict[tuple[str, str], Any] = {}
    for tract in tracts:
        acres = _tract_gross_acres(tract)
        legal = ""
        if tract.tract_legal_description and tract.tract_legal_description.value:
            legal = re.sub(r"\s+", " ", str(tract.tract_legal_description.value)).strip().lower()[:60]
        key = (str(acres), legal)
        if key not in best or completeness(tract) > completeness(best[key]):
            best[key] = tract
    return list(best.values())


_TRAILING_DECIMAL_RE = re.compile(r"(\d*\.\d+)\s*$")


def _seller_wi_value(operating_interest_text: str | None) -> Fraction | None:
    """Working-interest-table OI cells print the column's decimal value last
    (".62500000"), sometimes with a garbled formula fragment merged in front
    of it by OCR/transcription. Try the full expression first; if that fails,
    fall back to the trailing printed decimal — for the WI table specifically,
    that trailing number IS the column value."""
    value = parse_fraction_text(operating_interest_text)
    if value is not None:
        return value
    if not operating_interest_text:
        return None
    match = _TRAILING_DECIMAL_RE.search(str(operating_interest_text).strip())
    if match:
        try:
            value = Fraction(match.group(1))
        except (ValueError, ZeroDivisionError):
            return None
        return value if 0 <= value <= 1 else None
    return None


def resolve_seller_wi(tract: Any) -> tuple[Fraction | None, bool]:
    """The Seller's WORKING interest for one tract, validated so a net-revenue
    value can never silently masquerade as the working interest.

    Returns (value, needs_review):
      - (wi, False)  — OI column parsed and exceeds the NRI (the normal case;
        NRI = WI reduced by royalty burdens, so leasehold WI > NRI).
      - (wi, True)   — OI column was garbled/swapped (missing, unparseable, or
        <= NRI, i.e. it held the NRI calculation), and the WI was recovered
        deterministically from the NRI-calculation formula via
        derive_wi_from_nri_formula's checksum. Flag for manual verification.
      - (None, True) — Seller row exists but no safe WI could be resolved;
        the tract must be excluded pending manual review.
      - (None, False) — tract has no Seller working-interest row at all.
    """
    swi = tract.seller_working_interest
    if not swi:
        return None, False
    oi_value = _seller_wi_value(swi.operating_interest_text)
    nri_value = _seller_wi_value(swi.net_revenue_interest_text)
    if oi_value is not None and (nri_value is None or oi_value > nri_value):
        return oi_value, False
    for candidate_text in (swi.operating_interest_text, swi.net_revenue_interest_text):
        derived = derive_wi_from_nri_formula(candidate_text, nri_value)
        if derived is not None:
            return derived, True
    return None, True


def _seller_nri_value(tract: Any) -> Fraction | None:
    """The Seller's NET REVENUE interest for a tract, read directly from the
    working-interest table's Seller row (the opinion already computed it —
    e.g. Cox ".66203704"). Parsed with the same tolerance as the WI column."""
    swi = tract.seller_working_interest
    if not swi:
        return None
    return _seller_wi_value(swi.net_revenue_interest_text)


def _rows_from_tracts(file_number: str, tracts: list[Any]) -> tuple[list[LeaseTractRow], list[str]]:
    """One LeaseTractRow PER TRACT built from the Seller's own final figures in
    the opinion's working-interest table — the Seller's working interest and
    net revenue interest are already the tract-level answers, so net acres =
    tract_gross x Seller_WI and net revenue acres = tract_gross x Seller_NRI.

    This deliberately does NOT reconstruct the interest from per-owner mineral
    and royalty fractions: those tables have dozens of rows and any single
    unparseable fraction used to silently drop the whole tract (the Cox tract
    disappeared when one re-extraction returned zero royalty rows). mi_value is
    fixed at 1 and royalty is derived so nri_value == Seller_NRI/Seller_WI,
    keeping the LeaseTractRow formulas (net_acres = gross*mi*wi;
    net_rev_acres = net_acres*(1-royalty-orri)) exact.
    """
    rows: list[LeaseTractRow] = []
    issues: list[str] = []
    for tract in tracts:
        wi_value, needs_review = resolve_seller_wi(tract)
        if wi_value is None:
            if needs_review:
                oi_text = (
                    tract.seller_working_interest.operating_interest_text
                    if tract.seller_working_interest else None
                )
                issues.append(
                    f"{file_number}: Seller working interest could not be safely resolved "
                    f"(OI text: {str(oi_text)[:80]!r}) — tract EXCLUDED from computed totals "
                    f"pending manual review."
                )
            continue
        if needs_review:
            issues.append(
                f"{file_number}: Seller WORKING interest {float(wi_value):.8f} was derived "
                f"from the NRI-calculation formula (the opinion's OI column was garbled in "
                f"transcription) — verify against the opinion's working-interest column."
            )
        gross_acres = _tract_gross_acres(tract)
        if gross_acres is None:
            continue

        nri_value = _seller_nri_value(tract)
        if nri_value is None or wi_value == 0:
            # No usable Seller NRI: fall back to nri == wi (royalty burden
            # unknown) and flag, rather than dropping the tract's WI entirely.
            royalty = Fraction(0)
            issues.append(
                f"{file_number}: Seller net revenue interest could not be read from the "
                f"working-interest table — NRI shown equals WI (royalty burden unresolved); "
                f"verify against the opinion."
            )
        else:
            # nri_value = wi_value * (1 - royalty)  ->  royalty = 1 - nri/wi.
            royalty = Fraction(1) - (nri_value / wi_value)
            if royalty < 0:
                royalty = Fraction(0)

        rows.append(
            LeaseTractRow(
                lease_no=file_number,
                tract_gross_acres=gross_acres,
                mi_value=Fraction(1),
                wi_value=wi_value,
                royalty=royalty,
                orri_burdens=Fraction(0),
            )
        )
    return rows, issues


@dataclass
class OwnershipBasis:
    rows: list[LeaseTractRow]
    unit_gross_acres: Fraction | None
    source_file_number: str | None
    cert_date: date | None
    chosen_file_numbers: list[str] = field(default_factory=list)
    chain_notes: list[str] = field(default_factory=list)
    review_issues: list[str] = field(default_factory=list)


def _basis_from_group(
    group: list[tuple[str, TitleOpinionExtraction]],
) -> tuple[list[LeaseTractRow], Fraction, str, date | None, list[str]] | None:
    """Newest-first walk of one tract chain: the first opinion whose
    de-duplicated tracts yield parseable ownership rows AND gross acreage wins.
    Certification date sorts first; letter date breaks ties (a supplement often
    re-certifies through the same date as the original it revises). Returns
    None when no opinion in the chain resolves."""
    ordered = sorted(
        group,
        key=lambda pair: (
            _opinion_cert_date(pair[1]) or date.min,
            _opinion_letter_date(pair[1]) or date.min,
        ),
        reverse=True,
    )
    for file_number, extraction in ordered:
        tracts = _dedupe_tracts(extraction.tracts)
        gross = Fraction(0)
        for tract in tracts:
            acres = _tract_gross_acres(tract)
            if acres is not None:
                gross += acres
        rows, issues = _rows_from_tracts(file_number, tracts)
        if rows and gross > 0:
            return rows, gross, file_number, _opinion_cert_date(extraction), issues
    return None


def select_ownership_basis(
    manifest: UnitManifest,
    to_extractions: dict[str, TitleOpinionExtraction],
) -> OwnershipBasis:
    """Pick the aggregation basis. Opinions are grouped by their analyst-
    assigned tract_chain label (multi-tract units get one Original->Supplement
    chain per tract, e.g. Cox / Kramer / Brumbaugh); within each chain the
    newest opinion with machine-readable ownership controls, and rows/acreage
    are aggregated ACROSS chains. Unlabeled opinions all fall into a single
    default chain, which reproduces the pre-existing newest-opinion-wins
    behavior for single-tract units. Returns empty rows / None acreage when
    nothing resolves (reconciliation stays NOT_COMPUTED rather than emitting a
    fabricated zero)."""
    chains: dict[str, list[tuple[str, TitleOpinionExtraction]]] = {}
    for to_ref in manifest.title_opinions:
        extraction = to_extractions.get(to_ref.file_number)
        if not extraction or extraction.error:
            continue
        chains.setdefault(to_ref.tract_chain or "", []).append(
            (to_ref.file_number, extraction)
        )
    if not chains:
        return OwnershipBasis([], None, None, None)

    all_rows: list[LeaseTractRow] = []
    total_gross = Fraction(0)
    chosen: list[str] = []
    chain_notes: list[str] = []
    review_issues: list[str] = []
    latest_cert: date | None = None

    for chain_label in sorted(chains):
        resolved = _basis_from_group(chains[chain_label])
        if resolved is None:
            if chain_label:
                chain_notes.append(
                    f"{chain_label}: no opinion in this chain yielded parseable "
                    f"ownership + acreage — tract EXCLUDED from computed totals"
                )
                review_issues.append(
                    f"{chain_label}: tract excluded from computed totals — resolve the "
                    f"Seller interest for this tract manually."
                )
            continue
        rows, gross, file_number, cert, issues = resolved
        all_rows.extend(rows)
        total_gross += gross
        chosen.append(file_number)
        review_issues.extend(issues)
        if cert and (latest_cert is None or cert > latest_cert):
            latest_cert = cert
        # One tract per chain after dedupe — surface the Seller WI per chain.
        wi_values = sorted({float(r.wi_value) for r in rows})
        wi_text = "/".join(f"{v:.8f}" for v in wi_values)
        label = f"{chain_label}: " if chain_label else ""
        chain_notes.append(
            f"{label}{file_number}"
            + (f" (cert {cert.isoformat()})" if cert else "")
            + f", {float(gross):g} gross acres, Seller WI {wi_text}"
        )

    if not all_rows or total_gross <= 0:
        return OwnershipBasis([], None, None, None, chosen, chain_notes, review_issues)
    return OwnershipBasis(
        all_rows, total_gross, ", ".join(chosen), latest_cert, chosen, chain_notes,
        review_issues,
    )


def build_review_flags(
    manifest: UnitManifest,
    to_extractions: dict[str, TitleOpinionExtraction],
    basis: "OwnershipBasis",
    reconciliation: "ReconciliationResult",
    controlling_date: date,
    xref_to_numbers: list[str],
    supplemental_search_complete: bool = False,
) -> "DDReviewFlags":
    """Assemble the Summary-tab narrative. Potential Defects carries only
    title defects (none are machine-detected today, so it stays empty ->
    "None identified" unless a human adds one). Outstanding Curative
    Requirements carries the controlling opinions' own outstanding
    requirements plus process gaps (unparsed/missing opinions, and the
    supplemental-search instruction unless the search is already done).
    The leasehold-vs-wellbore reconciliation delta is a Section Note, not a
    defect — a JOA/non-consent uplift is expected, not a title failure."""
    from src.dd.ddr_writer import DDReviewFlags

    flags = DDReviewFlags()

    # --- Curative: the controlling opinions' outstanding requirements ------
    seen_requirements: set[str] = set()
    for file_number in basis.chosen_file_numbers:
        extraction = to_extractions.get(file_number)
        if not extraction:
            continue
        for tract in extraction.tracts:
            for requirement in tract.requirements:
                text = (requirement.value or "").strip()
                if text and text not in seen_requirements:
                    seen_requirements.add(text)
                    flags.curative_requirements.append(f"{file_number}: {text}")

    # --- Curative: Seller-interest resolution issues from the basis --------
    flags.curative_requirements.extend(basis.review_issues)

    # --- Curative: process gaps ---------------------------------------------
    parse_errors = [
        to.file_number
        for to in manifest.title_opinions
        if (ext := to_extractions.get(to.file_number)) and ext.error
    ]
    if parse_errors:
        flags.curative_requirements.append(
            f"Title opinion(s) failed to parse and need manual review: {', '.join(parse_errors)}."
        )
    provided = {t.file_number for t in manifest.title_opinions}
    n_expected = len(xref_to_numbers)
    n_provided = len(provided)
    if n_expected > n_provided:
        flags.curative_requirements.append(
            f"The Lease-to-Well XREF lists {n_expected} title opinion file number(s) for this "
            f"unit ({', '.join(xref_to_numbers)}); {n_provided} PDF(s) were provided and parsed. "
            f"Confirm every tract opinion is accounted for and obtain any missing PDFs."
        )
    if not supplemental_search_complete:
        flags.curative_requirements.append(
            f"Run supplemental title on {manifest.seller_name or 'the Seller'} in "
            f"{manifest.county or 'the'} County from {controlling_date.isoformat()} (controlling "
            f"certification date) to present."
        )

    # --- Section notes: reconciliation outcome + figure provenance ---------
    if reconciliation.wi_status == "NOT_COMPUTED" or reconciliation.nri_status == "NOT_COMPUTED":
        flags.section_notes.append(
            "WI/NRI could not be computed from the available title opinions "
            "(no parseable Seller interest + acreage). Verify Seller's interest manually."
        )
    elif reconciliation.wi_status == "N/A" or reconciliation.nri_status == "N/A":
        flags.section_notes.append(
            f"LEASEHOLD vs WELLBORE interest: the net-acre-weighted LEASEHOLD interest "
            f"computed from the controlling title opinions is WI "
            f"{float(reconciliation.computed_wi):.8f} / NRI "
            f"{float(reconciliation.computed_nri):.8f}. The Well List PSA figure (WI "
            f"{float(reconciliation.represented_wi):.8f} / NRI "
            f"{float(reconciliation.represented_nri):.8f}) is a WELLBORE interest, which "
            f"includes non-consent/JOA uplift earned by operating — a different quantity, "
            f"so no delta is computed between them and the difference is NOT a title "
            f"defect. Leasehold-to-leasehold reconciliation is N/A because no leasehold "
            f"PSA figure was provided."
        )
    elif reconciliation.wi_status == "WARNING" or reconciliation.nri_status == "WARNING":
        flags.section_notes.append(
            f"Computed leasehold WI {float(reconciliation.computed_wi):.6f} / "
            f"NRI {float(reconciliation.computed_nri):.6f} vs represented leasehold "
            f"WI {float(reconciliation.represented_wi):.6f} / "
            f"NRI {float(reconciliation.represented_nri):.6f} — delta exceeds tolerance; "
            f"reconcile the tract interests against the opinions before delivery."
        )
    if basis.chain_notes:
        flags.section_notes.append(
            "Ownership basis (controlling opinion per tract): " + "; ".join(basis.chain_notes)
            + ". Tract gross acres derive from the title opinions' legal descriptions — "
            "verify against an independent survey/plat."
        )
    flags.section_notes.append(
        "Acreage, boundaries and on-the-ground location are not certified here and require "
        "an independent survey."
    )
    return flags


# ---------------------------------------------------------------------------
# End-to-end orchestrator
# ---------------------------------------------------------------------------

@dataclass
class DDPipelineResult:
    output_dir: Path
    manifest: UnitManifest
    manifest_path: Path
    to_extractions: dict[str, TitleOpinionExtraction]
    controlling_certification_date: date
    qa_exceptions: list[QAException]
    ddr_result: DDRWriteResult
    summary: dict[str, Any] = field(default_factory=dict)


def run_dd_pipeline_for_unit(
    unit_name: str,
    project_log_path: str | Path | None = None,
    xref_path: str | Path | None = None,
    well_list_path: str | Path | None = None,
    ddr_template_path: str | Path = "",
    output_root: str | Path = "data/output/dd",
    to_files_dir: str | Path | None = None,
    supplemental_records: list[SourceDocument] | None = None,
    progress_callback: ProgressCallback | None = None,
    manifest_override: UnitManifest | None = None,
    uploaded_title_opinion_pdfs: list[str | Path] | None = None,
    runsheet_clean_note: str | None = None,
    supplemental_search_complete: bool = False,
    lease_document_dir: str | Path | None = None,
    lease_document_cache_dir: str | Path | None = None,
    unit_folder: str | Path | None = None,
    dpu_work_dir: str | Path | None = None,
    dpu_contract_no: str = "K1400813",
    stage_submission_dir: str | Path | None = None,
) -> DDPipelineResult:
    """Run the full DD pipeline for one unit: build manifest, parse available
    title opinions, resolve the controlling certification date, filter and QA
    the supplemental document list (if supplied), aggregate WI/NRI, and fill
    the DDR template. Mirrors MOR's run_full_pipeline_from_dataframe shape but
    is unit-scoped, not document-list-scoped, since DD starts from a unit
    name rather than a document list.

    manifest_override lets callers skip the 3 reference workbooks entirely
    (project_log_path/xref_path/well_list_path become optional) by supplying
    an already-built UnitManifest — e.g. one assembled ad hoc from title
    opinion filenames when the client hasn't provided Project Log/Xref/Well
    List yet. Aggregation/reconciliation against a Well List baseline is
    skipped automatically in that case (manifest.represented_interest is None).
    """
    output_dir = Path(output_root) / unit_name
    output_dir.mkdir(parents=True, exist_ok=True)

    if manifest_override is not None:
        manifest = manifest_override
        manifest_path, _build_log_path = write_manifest(manifest, {"unit_name": unit_name}, output_dir.parent / unit_name)
        if manifest.represented_interest is None:
            _emit(
                progress_callback,
                "warn",
                f"Unit {unit_name} — no reference workbooks supplied; manifest built from title "
                f"opinion filenames only ({len(manifest.title_opinions)} title opinion(s)). "
                f"WI/NRI reconciliation against a Well List will be skipped.",
            )
        else:
            _emit(
                progress_callback,
                "ok",
                f"Unit {unit_name} — analyst-supplied manifest: {len(manifest.title_opinions)} "
                f"title opinion(s), {len(manifest.leases)} lease(s), Well List baseline present",
            )
    else:
        _emit(progress_callback, "working", f"Unit {unit_name} — building manifest from reference workbooks...")
        manifest, manifest_path, _build_log_path = build_and_write_manifest(
            unit_name=unit_name,
            project_log_path=project_log_path,
            xref_path=xref_path,
            well_list_path=well_list_path,
            output_root=output_dir.parent,
            to_files_dir=to_files_dir,
        )
        _emit(
            progress_callback,
            "ok",
            f"Unit {unit_name} — manifest built: {len(manifest.title_opinions)} title opinion(s), "
            f"{len(manifest.leases)} lease(s)",
        )

    # Capture the XREF-derived title opinion file numbers before any upload
    # override replaces them, so the Summary review flags can still report how
    # many opinions the XREF expected for this unit vs. how many were provided.
    xref_to_numbers = [to.file_number for to in manifest.title_opinions]

    # When the analyst selected a single unit and uploaded that unit's TO PDFs
    # directly, those PDFs are authoritative: bind them to the manifest so they
    # get parsed even though their descriptive filenames carry no xref file
    # number for glob-based probing to match.
    if uploaded_title_opinion_pdfs:
        set_title_opinions_from_uploads(manifest, uploaded_title_opinion_pdfs)
        _emit(
            progress_callback,
            "ok",
            f"Unit {unit_name} — {len(manifest.title_opinions)} uploaded title opinion PDF(s) "
            f"bound to this unit for parsing",
        )

    to_extractions: dict[str, TitleOpinionExtraction] = {}
    n_no_pdf = 0
    for to_ref in manifest.title_opinions:
        _emit(progress_callback, "working", f"Title opinion {to_ref.file_number} — processing...")
        extraction = parse_title_opinion(
            to_ref,
            target_unit_name=unit_name,
            seller_name=manifest.seller_name,
            work_dir=output_dir / "title_opinion_work",
            # Persistent JSON cache: reruns reuse prior successful extractions
            # (failures are never cached), so results are reproducible across
            # runs and transient API errors only cost a retry of that one PDF.
            cache_dir=Path("data/working/dd_to_cache"),
        )
        to_extractions[to_ref.file_number] = extraction
        if not extraction.pdf_available:
            n_no_pdf += 1
            _emit(
                progress_callback,
                "warn",
                f"Title opinion {to_ref.file_number} — no source PDF found, skipped",
            )
        elif extraction.error:
            _emit(progress_callback, "err", f"Title opinion {to_ref.file_number} — {extraction.error}")
        else:
            cert_dates = [
                t.certification_date.value for t in extraction.tracts if t.certification_date
            ]
            cert_str = cert_dates[0] if cert_dates else "n/a"
            _emit(
                progress_callback,
                "ok",
                f"Title opinion {to_ref.file_number} — extracted, certification date {cert_str}",
            )

    qa_exceptions: list[QAException] = []
    try:
        controlling_date = resolve_controlling_certification_date(manifest, to_extractions)
    except SupplementalScopeError as exc:
        qa_exceptions.append(controlling_certification_date_qa_exception(manifest, exc))
        _emit(progress_callback, "err", f"Unit {unit_name} — {exc}")
        raise

    manifest.controlling_certification_date = controlling_date
    _emit(
        progress_callback,
        "ok",
        f"Unit {unit_name} — controlling certification date resolved: {controlling_date.isoformat()}",
    )

    # Choose the aggregation basis (newest opinion with clean, parseable
    # ownership + acreage) and derive unit gross acres from it, unless the
    # analyst pinned unit_gross_acres manually. This closes the WI/NRI
    # reconciliation that otherwise reports NOT_COMPUTED for lack of a
    # denominator, while de-duplicating over-segmented tracts.
    basis = select_ownership_basis(manifest, to_extractions)
    if basis.source_file_number:
        _emit(
            progress_callback,
            "ok",
            f"Unit {unit_name} — ownership basis: title opinion {basis.source_file_number}"
            + (f" (cert {basis.cert_date.isoformat()})" if basis.cert_date else "")
            + f", {float(basis.unit_gross_acres):g} gross acres, {len(basis.rows)} tract-row(s)",
        )
        if not manifest.unit_gross_acres:
            manifest.unit_gross_acres = str(basis.unit_gross_acres)
    else:
        _emit(
            progress_callback,
            "warn",
            f"Unit {unit_name} — no title opinion yielded parseable Seller interest + "
            f"acreage; WI/NRI reconciliation will be skipped (NOT_COMPUTED)",
        )

    records = supplemental_records or []
    if records:
        deduplicate_documents(records)
        classify_documents(records)
        apply_supplemental_scope_filter(records, controlling_date, manifest.seller_name)
        qa_exceptions.extend(run_qa(records))
        in_scope = sum(1 for r in records if r.status != ClassificationStatus.REDLINE)
        _emit(
            progress_callback,
            "ok",
            f"Unit {unit_name} — {len(records)} supplemental instrument(s) reviewed, "
            f"{in_scope} in scope after {controlling_date.isoformat()}",
        )

    aggregation = reconciliation = None
    if manifest.unit_gross_acres and manifest.represented_interest:
        rows = basis.rows
        try:
            aggregation, reconciliation, recon_exceptions = run_dd_aggregation(manifest, rows)
            qa_exceptions.extend(recon_exceptions)
            if reconciliation.wi_status == "N/A":
                _emit(
                    progress_callback,
                    "ok",
                    f"Unit {unit_name} — leasehold WI {float(reconciliation.computed_wi):.8f} / "
                    f"NRI {float(reconciliation.computed_nri):.8f} computed from title; PSA "
                    f"wellbore comparison N/A (different interest basis, not a defect)",
                )
            else:
                _emit(
                    progress_callback,
                    "ok" if reconciliation.wi_status == "PASS" and reconciliation.nri_status == "PASS" else "warn",
                    f"Unit {unit_name} — WI {reconciliation.wi_status}, NRI {reconciliation.nri_status} "
                    f"vs. Well List",
                )
        except AggregationError as exc:
            logger.warning("DD aggregation skipped for %s: %s", unit_name, exc)
            _emit(progress_callback, "warn", f"Unit {unit_name} — aggregation skipped: {exc}")

    lease_review_rows = build_lease_review_rows(manifest, to_extractions)
    to_summaries = build_to_summaries(manifest, to_extractions)
    for summary in to_summaries:
        summary["controlling"] = summary["file_number"] in basis.chosen_file_numbers

    # Per-lease MI/WI/royalty/legal from the controlling opinions' MINERALS
    # section (Collin items 1-2): fills the 26/30 leases the lease-block match
    # left blank, matching each lease's lessor to its mineral owner. Then run
    # the MI-sums-to-1 and Seller-WI gates.
    controlling = {
        fn: to_extractions[fn] for fn in basis.chosen_file_numbers if fn in to_extractions
    }
    lease_document_details: dict[str, dict[str, Any]] = {}
    if lease_document_dir is not None:
        from src.dd.lease_document_source import build_lease_document_details
        lease_document_details = build_lease_document_details(
            lease_document_dir, manifest.leases,
            work_dir=output_dir / "lease_document_work",
            cache_dir=lease_document_cache_dir, progress=progress_callback,
        )
        _emit(progress_callback, "ok",
              f"Unit {unit_name} — {len(lease_document_details)} lease document(s) read from the new-files folder")
    gate_results, lease_conflicts = enrich_lease_rows_with_details(
        lease_review_rows, manifest, controlling, reconciliation, lease_document_details,
    )

    # Record Book/Page from the unit's recorded Declaration of Pooled Unit and
    # its Amendment (Exhibit "A" is the authoritative recording reference).
    from src.dd.dd_pending import PendingRegistry
    pending_registry = PendingRegistry()
    dpu_notes: list[str] = []
    dpu_recording_map: dict[str, tuple] = {}
    if unit_folder is not None:
        from src.dd.dpu_source import apply_recording_to_rows, load_unit_dpu, reconcile_lease_set
        dpu = load_unit_dpu(
            unit_folder,
            work_dir=Path(dpu_work_dir) if dpu_work_dir else (output_dir / "dpu_work"),
            contract_no=dpu_contract_no,
        )
        applied = apply_recording_to_rows(lease_review_rows, dpu, pending_registry)
        dpu_notes = list(dpu.notes)
        # The declaration is historical; the XREF is the active list. Record the
        # difference so the exclusions are auditable, not silent.
        dpu_notes.extend(reconcile_lease_set(
            dpu, [str(r.get("lease_no")) for r in lease_review_rows]))
        # Exhibit A is the authority for every recording reference (the
        # "Volume 37 vs 371" class of defect is decided against it).
        dpu_recording_map = {l.lease_no: (l.record_book, l.record_page)
                             for l in dpu.leases}
        if dpu.dpu_source:
            _emit(progress_callback, "ok",
                  f"Unit {unit_name} — Record Book/Page for {len(applied)}/{len(lease_review_rows)} "
                  f"lease(s) from {dpu.dpu_source}"
                  + (f" + {', '.join(dpu.amendment_sources)}" if dpu.amendment_sources else ""))
    _register_pending_reasons(lease_review_rows, pending_registry)

    if aggregation is None or reconciliation is None:
        from src.dd.unit_aggregation import AggregationResult, ReconciliationResult
        from fractions import Fraction

        # NOT_COMPUTED, never "PASS" — aggregation didn't run (missing
        # unit_gross_acres and/or represented_interest, or AggregationError),
        # so there is nothing to compare against the Well List. Reporting
        # "PASS" here would tell a landman the reconciliation succeeded when
        # it was never attempted.
        zero = Fraction(0)
        aggregation = AggregationResult(zero, zero, zero, zero, zero, [])
        reconciliation = ReconciliationResult(
            zero, zero, zero, zero, zero, zero, "NOT_COMPUTED", "NOT_COMPUTED"
        )
        qa_exceptions.append(
            QAException(
                severity="WARNING",
                code="DD_RECONCILIATION_NOT_COMPUTED",
                message=(
                    "WI/NRI reconciliation against the Well List was not computed "
                    "(missing unit_gross_acres and/or represented_interest, or "
                    "aggregation failed) — this is not a pass, it was never run."
                ),
                field="reconciliation",
            )
        )

    review_flags = build_review_flags(
        manifest, to_extractions, basis, reconciliation, controlling_date, xref_to_numbers,
        supplemental_search_complete=supplemental_search_complete,
    )
    # Surface any TO-vs-lease-document conflicts (never silently resolved).
    for conflict in lease_conflicts:
        review_flags.potential_defects.append(f"Source conflict — {conflict}")
    # Leases the DPU's Amendment added to the unit ("inadvertently excluded").
    for note in dpu_notes:
        review_flags.section_notes.append(f"DPU Amendment — {note}")
    # Fold QA-gate failures into the review narrative and QA exceptions so a
    # failing gate blocks a clean "done" and is itemized with its location.
    for gate in gate_results:
        if not gate.passed:
            review_flags.potential_defects.append(f"QA gate '{gate.name}': {gate.detail}")
            for loc in gate.locations:
                review_flags.potential_defects.append(loc)
            qa_exceptions.append(
                QAException(severity="WARNING", code=f"DD_GATE_{gate.name.upper()}",
                            message=gate.detail, field=gate.name)
            )

    # Cell-level document+page provenance, located INDEPENDENTLY of the
    # extraction (src/dd/provenance): for each MI/WI the opinion where THIS
    # owner's value actually appears, for recording the DPU. A cite names the
    # document that contains the value, not the one the extractor guessed.
    provenance_store = _build_provenance_store(
        lease_review_rows, controlling, to_files_dir, unit_folder,
        lease_document_dir, dpu_recording_map)

    ddr_result = fill_ddr_template(
        template_path=ddr_template_path,
        manifest=manifest,
        output_dir=output_dir,
        aggregation=aggregation,
        reconciliation=reconciliation,
        lease_review_rows=lease_review_rows,
        provenance_store=provenance_store,
        runsheet_records=records,
        runsheet_note=(
            f"Supplemental title from {controlling_date.isoformat()} (controlling title "
            f"opinion certification date) to present, limited to the interest of "
            f"{manifest.seller_name or 'the Seller'}."
        ),
        to_summaries=to_summaries,
        review_flags=review_flags,
        runsheet_clean_note=runsheet_clean_note,
        pending_registry=pending_registry,
    )

    # MANDATORY final gate. Every unit, every run — a gate that runs when someone
    # remembers is a suggestion, and Maxwell shipped ~30 correction cycles' worth
    # of defects that these rules now catch mechanically. The DDR is written
    # either way; `validation_ready` says whether it may be SENT.
    from src.dd.ddr_validator import DDRNotReadyError, run_final_validation

    validation = run_final_validation(
        ddr_result.output_path,
        template_path=ddr_template_path,
        allowlist=_validation_allowlist(manifest, lease_review_rows),
        dpu_by_lease=dpu_recording_map,
        documents_available=_documents_on_disk(unit_folder),
        client_name=manifest.client_name,
        source_roots=_validation_source_roots(unit_folder, to_files_dir, lease_document_dir),
    )
    _emit(progress_callback, "ok" if validation.ready else "error",
          f"Unit {unit_name} — validation: {validation.summary()}")
    for finding in validation.failures[:20]:
        _emit(progress_callback, "error", f"  {finding.describe()}")
    if not validation.ready:
        review_flags.potential_defects.append(
            f"VALIDATION NOT READY — {validation.summary()}. See the sidecar report next to "
            "the DDR; this workbook must not be sent until every FAIL is resolved.")

    # FINAL step: assemble the ready-to-upload PLM submission tree INSIDE the
    # unit's own project folder (never a scratch dir). Runs whenever the real
    # unit folder is known, or an explicit target is supplied.
    if unit_folder is not None or stage_submission_dir is not None:
        _stage_submission_package(
            unit_name=unit_name,
            ddr_path=ddr_result.output_path,
            unit_folder=unit_folder,
            to_files_dir=to_files_dir,
            stage_submission_dir=stage_submission_dir,
            dpu_contract_no=dpu_contract_no,
            progress_callback=progress_callback,
        )

    summary = {
        "unit_name": unit_name,
        "title_opinions_total": len(manifest.title_opinions),
        "title_opinions_no_pdf": n_no_pdf,
        "controlling_certification_date": controlling_date.isoformat(),
        "qa_errors": sum(e.severity == "ERROR" for e in qa_exceptions),
        "qa_warnings": sum(e.severity == "WARNING" for e in qa_exceptions),
        "reconciliation_wi_status": reconciliation.wi_status,
        "reconciliation_nri_status": reconciliation.nri_status,
        "output_path": str(ddr_result.output_path),
    }
    write_json(output_dir / "dd_processing_summary.json", summary)
    _print_dd_completion(summary)
    _emit(progress_callback, "ok", f"Unit {unit_name} — DDR filled: {ddr_result.output_path.name}")

    return DDPipelineResult(
        output_dir=output_dir,
        manifest=manifest,
        manifest_path=manifest_path,
        to_extractions=to_extractions,
        controlling_certification_date=controlling_date,
        qa_exceptions=qa_exceptions,
        ddr_result=ddr_result,
        summary=summary,
    )


def _stage_submission_package(
    unit_name: str,
    ddr_path: Path,
    unit_folder: str | Path | None,
    to_files_dir: str | Path | None,
    stage_submission_dir: str | Path | None,
    dpu_contract_no: str | None,
    progress_callback: ProgressCallback | None,
) -> Path | None:
    """Build the ready-to-upload PLM submission tree INSIDE the unit's own
    project folder (the parent of its FILES folder), copying from FILES and
    leaving it untouched. Delegates to submission_packager.package_unit_submission,
    which prints the absolute path of the created tree.

    An explicit stage_submission_dir still overrides the location (used by tests)."""
    from src.dd.submission_packager import package_unit_submission

    # Locate the real project unit folder — the parent of FILES.
    project_folder = None
    if unit_folder and (Path(unit_folder) / "FILES").exists():
        project_folder = Path(unit_folder)
    elif to_files_dir and Path(to_files_dir).name.upper() == "FILES":
        project_folder = Path(to_files_dir).parent
    elif unit_folder:
        project_folder = Path(unit_folder)

    if stage_submission_dir is not None:
        # Explicit override: honour it, but still copy the finished DDR in.
        project_folder = Path(stage_submission_dir)

    if project_folder is None or not (project_folder / "FILES").exists():
        _emit(progress_callback, "warn",
              f"Unit {unit_name} — submission packager skipped: no FILES folder located.")
        return None

    root, plan = package_unit_submission(
        unit_folder=project_folder,
        ddr_path=Path(ddr_path),
        unit_name=unit_name,
        unit_dpu_contract=dpu_contract_no,
    )
    _emit(progress_callback, "ok",
          f"Unit {unit_name} — submission package created at {root.resolve()}: "
          f"{len(plan.placed)} file(s) placed, {len(plan.missing)} missing, "
          f"{len(plan.decisions)} decision(s).")
    return root


def _print_dd_completion(summary: dict[str, Any]) -> None:
    lines = [
        "",
        "=== PLM Due Diligence Pipeline Complete ===",
        f"  Unit                : {summary['unit_name']}",
        f"  Title Opinions      : {summary['title_opinions_total']} total, "
        f"{summary['title_opinions_no_pdf']} with no source PDF",
        f"  Certification Date  : {summary['controlling_certification_date']}",
        f"  WI Reconciliation   : {summary['reconciliation_wi_status']}",
        f"  NRI Reconciliation  : {summary['reconciliation_nri_status']}",
        f"  QA errors/warnings  : {summary['qa_errors']}/{summary['qa_warnings']}",
        f"  Output              : {summary['output_path']}",
        "=============================================",
        "",
    ]
    print("\n".join(lines))
