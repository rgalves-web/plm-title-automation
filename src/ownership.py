"""Chain-of-title ownership ledger engine.

Party names are normalised to canonical keys so minor typographical
differences ("John Smith." vs "JOHN SMITH") and non-identity descriptors
("and wife", "trustee") do not fragment the ownership table.
Arithmetic uses fractions.Fraction throughout — never floats.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from fractions import Fraction
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from rapidfuzz import fuzz
from rapidfuzz import process as fuzz_process

from src.lease_engine import is_oil_and_gas_lease
from src.schemas import ClassificationStatus, LeaseStatus, ProjectMetadata, SourceDocument
from src.utils import get_logger, timestamp, write_json

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Name-normalisation constants
# ---------------------------------------------------------------------------

FUZZY_AUTO_UNIFY = 93       # score >= this  → auto-unify silently
FUZZY_POSSIBLE_MATCH = 80   # score in [this, FUZZY_AUTO_UNIFY) → flag for review

_SUFFIX_NORM: dict[str, str] = {
    "JR.": "JR",
    "SR.": "SR",
    "JUNIOR": "JR",
    "SENIOR": "SR",
}

# Stripped from END of name for canonical key only; display name is unchanged.
_NON_IDENTITY_RE = re.compile(
    r"[,\s]+"
    r"(AND HUSBAND AND WIFE|HUSBAND AND WIFE|AND WIFE|AND HUSBAND"
    r"|A SINGLE WOMAN|A SINGLE MAN"
    r"|INDEPENDENT EXECUTOR|PERSONAL REPRESENTATIVE"
    r"|DECEASED|TRUSTEE|PLAINTIFF|DEFENDANT)"
    r"\s*$",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Public: canonical party key
# ---------------------------------------------------------------------------

def canonical_party_key(name: str) -> str:
    """Normalised key for ledger matching — internal use only.

    Strips non-identity descriptors from the end, collapses whitespace,
    removes insignificant punctuation, uppercases, and normalises name
    suffixes.  Identity suffixes (JR, SR, II, III, IV) are preserved so
    a father and son remain distinct parties.
    """
    if not name:
        return ""
    key = " ".join(name.upper().split())
    key = re.sub(r'[.,"]+', " ", key)
    key = " ".join(key.split())
    key = " ".join(_SUFFIX_NORM.get(tok, tok) for tok in key.split())
    prev = None
    while key != prev:
        prev = key
        key = _NON_IDENTITY_RE.sub("", key).strip()
    return key


# ---------------------------------------------------------------------------
# Output models
# ---------------------------------------------------------------------------

class OwnershipEntry(BaseModel):
    party: str                     # display name from most-recent instrument
    source_instrument: str
    source_document_id: str
    interest_type: str             # "Fee - OGM" | "Working Interest" | "Royalty"
    interest_fraction: str         # "N/D" string
    interest_decimal: float        # float only for Excel; computation uses Fraction
    legal_description: str | None = None
    gross_acres: str | None = None
    section: str | None = None
    township: str | None = None
    range_: str | None = None
    status: str = "Open"
    needs_review: bool = False
    review_note: str | None = None
    comments: str | None = None


class TitleException(BaseModel):
    source_document_id: str
    instrument: str          # "POSSIBLE_NAME_MATCH" | "SUMMARY" | actual ref
    grantor: str
    gap_description: str


@dataclass
class OwnershipResult:
    entries: list[OwnershipEntry] = field(default_factory=list)
    exceptions: list[TitleException] = field(default_factory=list)
    ledger_total_fraction: str = "0/1"
    needs_review_count: int = 0
    party_aliases: dict[str, list[str]] = field(default_factory=dict)
    possible_name_matches: list[dict[str, Any]] = field(default_factory=list)

    @property
    def ledger_total(self) -> Fraction:
        return Fraction(self.ledger_total_fraction)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ownership_entries": len(self.entries),
            "ownership_total_interest": self.ledger_total_fraction,
            "title_exceptions": [e.model_dump() for e in self.exceptions],
            "ownership_needs_review": self.needs_review_count,
            "sum_equals_one": self.ledger_total == Fraction(1, 1),
            "party_aliases": self.party_aliases,
            "possible_name_matches": self.possible_name_matches,
        }


# ---------------------------------------------------------------------------
# Fraction parser
# ---------------------------------------------------------------------------

_UNDIVIDED_RE = re.compile(
    r"undivided\s+(\d+)\s*/\s*(\d+)\s+interest",
    re.IGNORECASE,
)
_BARE_FRACTION_RE = re.compile(r"\b(\d{1,4})\s*/\s*(\d{1,4})\b")


def _parse_fraction(conveyance: str) -> tuple[Fraction | None, bool]:
    m = _UNDIVIDED_RE.search(conveyance)
    if m:
        n, d = int(m.group(1)), int(m.group(2))
        if d > 0:
            return Fraction(n, d), False
    m = _BARE_FRACTION_RE.search(conveyance)
    if m:
        n, d = int(m.group(1)), int(m.group(2))
        if d > 0 and n <= d:
            return Fraction(n, d), True
    return None, True


def _is_patent(conveyance: str) -> bool:
    return conveyance.strip().lower().startswith("grant of:")


def _is_full_transfer(conveyance: str) -> bool:
    lower = conveyance.strip().lower()
    for prefix in ("arti to:", "the court orders:"):
        if lower.startswith(prefix):
            return True
    return False


def _instrument_ref(record: SourceDocument) -> str:
    if record.instrument_number:
        return record.instrument_number
    if record.book and record.page:
        return f"{record.book}/{record.page}"
    return record.source_document_id


# ---------------------------------------------------------------------------
# Name-matching helpers
# ---------------------------------------------------------------------------

def _register_party(
    canonical_key: str,
    display_name: str,
    party_display_names: dict[str, str],
    party_aliases: dict[str, list[str]],
) -> None:
    aliases = party_aliases.setdefault(canonical_key, [])
    if display_name not in aliases:
        aliases.append(display_name)
    party_display_names[canonical_key] = display_name


def _resolve_grantor(
    grantor: str,
    ledger: dict[str, Fraction],
    party_display_names: dict[str, str],
    party_aliases: dict[str, list[str]],
    result: OwnershipResult,
    instr: str,
    source_document_id: str,
) -> tuple[str | None, str]:
    """Resolve grantor to a ledger key.  Returns (key | None, match_type).

    match_type: 'exact' | 'fuzzy_unified' | 'possible_match' | 'not_found'
    Side-effects on result.exceptions / result.possible_name_matches.
    """
    grantor_key = canonical_party_key(grantor)
    if grantor_key in ledger:
        return grantor_key, "exact"

    if not ledger:
        return None, "not_found"

    match = fuzz_process.extractOne(
        grantor_key,
        list(ledger.keys()),
        scorer=fuzz.token_sort_ratio,
    )
    if match is None:
        return None, "not_found"

    candidate_key, score, _ = match
    candidate_display = party_display_names.get(candidate_key, candidate_key)

    if score >= FUZZY_AUTO_UNIFY:
        aliases = party_aliases.setdefault(candidate_key, [])
        for v in (grantor_key, grantor):
            if v not in aliases:
                aliases.append(v)
        logger.debug(
            "Fuzzy unified '%s' → '%s' (score=%d) at %s",
            grantor, candidate_display, score, instr,
        )
        return candidate_key, "fuzzy_unified"

    if score >= FUZZY_POSSIBLE_MATCH:
        result.possible_name_matches.append({
            "grantor": grantor,
            "candidate": candidate_display,
            "score": int(score),
            "instrument": instr,
            "source_document_id": source_document_id,
        })
        result.exceptions.append(TitleException(
            source_document_id=source_document_id,
            instrument="POSSIBLE_NAME_MATCH",
            grantor=grantor,
            gap_description=(
                f"Possible name match: '{grantor}' ≈ '{candidate_display}' "
                f"(score={int(score)}). Verify same party before proceeding."
            ),
        ))
        logger.warning(
            "Possible name match: '%s' ~ '%s' score=%d at %s — not auto-unified",
            grantor, candidate_display, score, instr,
        )
        return None, "possible_match"

    return None, "not_found"


# ---------------------------------------------------------------------------
# Chain-of-title ledger
# ---------------------------------------------------------------------------

def build_ownership_ledger(
    records: list[SourceDocument],
    section: str | None = None,
    township: str | None = None,
    range_: str | None = None,
) -> OwnershipResult:
    """Compute current ownership from INCLUDE_FULL records.

    Ledger keys are canonical_party_key() strings.
    Display names are stored separately and used in output entries.
    """
    result = OwnershipResult()

    fee_ledger: dict[str, Fraction] = {}
    royalty_ledger: dict[str, Fraction] = {}
    wi_ledger: dict[str, Fraction] = {}
    party_display_names: dict[str, str] = {}
    possible_match_grantee_keys: set[str] = set()

    eligible = [
        r for r in records
        if r.status == ClassificationStatus.INCLUDE_FULL and r.conveyance
    ]
    eligible.sort(key=lambda r: (
        r.effective_date or r.instrument_date or r.recording_date or date.max,
        r.source_document_id,
    ))

    for record in eligible:
        conveyance = record.conveyance or ""
        grantor = (record.grantor or "").strip()
        grantee = (record.grantee or "").strip()
        doc_type = (record.document_type or "").lower()
        instr = _instrument_ref(record)
        grantee_key = canonical_party_key(grantee)

        if grantee_key:
            _register_party(grantee_key, grantee, party_display_names, result.party_aliases)

        # ── OGL ──────────────────────────────────────────────────────────
        if is_oil_and_gas_lease(record):
            if record.lease_status in (LeaseStatus.EXPIRED, LeaseStatus.RELEASED):
                continue
            if record.lease_status == LeaseStatus.ACTIVE or record.lease_status is None:
                frac, _ = _parse_fraction(conveyance)
                if frac is None:
                    frac = Fraction(1, 1)
                wi_ledger[grantee_key] = wi_ledger.get(grantee_key, Fraction(0)) + frac
            continue

        # ── Royalty deed ──────────────────────────────────────────────────
        if "royalty" in doc_type and "release" not in doc_type:
            frac, _ = _parse_fraction(conveyance)
            if frac is None:
                result.needs_review_count += 1
                result.entries.append(OwnershipEntry(
                    party=grantee,
                    source_instrument=instr,
                    source_document_id=record.source_document_id,
                    interest_type="Royalty",
                    interest_fraction="?",
                    interest_decimal=0.0,
                    legal_description=record.legal_description,
                    gross_acres=record.acreage,
                    section=section, township=township, range_=range_,
                    needs_review=True,
                    review_note="Royalty quantum not parseable from conveyance.",
                ))
                continue
            royalty_ledger[grantee_key] = royalty_ledger.get(grantee_key, Fraction(0)) + frac
            continue

        # ── Patent / Government Grant ─────────────────────────────────────
        if _is_patent(conveyance):
            fee_ledger[grantee_key] = fee_ledger.get(grantee_key, Fraction(0)) + Fraction(1, 1)
            logger.debug("Patent: %s → %s 1/1 (%s)", grantor, grantee, instr)
            continue

        # ── Full ARTI transfer ────────────────────────────────────────────
        if _is_full_transfer(conveyance) and not re.search(r"undivided", conveyance, re.IGNORECASE):
            resolved_key, match_type = _resolve_grantor(
                grantor, fee_ledger, party_display_names, result.party_aliases,
                result, instr, record.source_document_id,
            )
            if resolved_key is None:
                if match_type == "possible_match":
                    possible_match_grantee_keys.add(grantee_key)
                result.exceptions.append(TitleException(
                    source_document_id=record.source_document_id,
                    instrument=instr,
                    grantor=grantor,
                    gap_description=(
                        f"Grantor '{grantor}' has no recorded interest "
                        f"but is conveying full interest to '{grantee}'."
                    ),
                ))
                logger.warning("Title gap at %s: grantor '%s' not in ledger", instr, grantor)
                continue
            grantor_balance = fee_ledger.get(resolved_key, Fraction(0))
            _move_interest(fee_ledger, resolved_key, grantee_key, grantor_balance)
            logger.debug("Full transfer: %s → %s %s (%s)", grantor, grantee, grantor_balance, instr)

        else:
            # ── Fractional transfer ───────────────────────────────────────
            frac, needs_review = _parse_fraction(conveyance)
            if frac is None:
                result.needs_review_count += 1
                result.entries.append(OwnershipEntry(
                    party=grantee,
                    source_instrument=instr,
                    source_document_id=record.source_document_id,
                    interest_type="Fee - OGM",
                    interest_fraction="?",
                    interest_decimal=0.0,
                    legal_description=record.legal_description,
                    gross_acres=record.acreage,
                    section=section, township=township, range_=range_,
                    needs_review=True,
                    review_note="Fractional quantum not parseable from conveyance.",
                ))
                continue

            resolved_key, match_type = _resolve_grantor(
                grantor, fee_ledger, party_display_names, result.party_aliases,
                result, instr, record.source_document_id,
            )
            if resolved_key is None:
                if match_type == "possible_match":
                    possible_match_grantee_keys.add(grantee_key)
                result.exceptions.append(TitleException(
                    source_document_id=record.source_document_id,
                    instrument=instr,
                    grantor=grantor,
                    gap_description=(
                        f"Grantor '{grantor}' has {fee_ledger.get(canonical_party_key(grantor), Fraction(0))} "
                        f"but is conveying {frac} to '{grantee}'."
                    ),
                ))
                logger.warning(
                    "Title gap at %s: grantor '%s' not in ledger, conveying %s",
                    instr, grantor, frac,
                )
                continue

            grantor_balance = fee_ledger.get(resolved_key, Fraction(0))
            if frac > grantor_balance:
                result.exceptions.append(TitleException(
                    source_document_id=record.source_document_id,
                    instrument=instr,
                    grantor=grantor,
                    gap_description=(
                        f"Grantor '{grantor}' has {grantor_balance} "
                        f"but is conveying {frac} to '{grantee}'."
                    ),
                ))
                logger.warning(
                    "Title gap at %s: grantor '%s' has %s, conveying %s",
                    instr, grantor, grantor_balance, frac,
                )
                continue

            _move_interest(fee_ledger, resolved_key, grantee_key, frac)
            logger.debug("Fractional: %s → %s %s (%s)", grantor, grantee, frac, instr)

    # ── Build OwnershipEntry list ─────────────────────────────────────────

    for canonical_key, frac in sorted(fee_ledger.items()):
        if frac > Fraction(0):
            display = party_display_names.get(canonical_key, canonical_key)
            is_review = canonical_key in possible_match_grantee_keys
            result.entries.append(OwnershipEntry(
                party=display,
                source_instrument=_last_instrument_for_party(canonical_key, eligible),
                source_document_id=_last_doc_id_for_party(canonical_key, eligible),
                interest_type="Fee - OGM",
                interest_fraction=str(frac),
                interest_decimal=float(frac),
                section=section, township=township, range_=range_,
                needs_review=is_review,
                review_note="Possible name match detected — verify grantor identity." if is_review else None,
            ))

    for canonical_key, frac in sorted(royalty_ledger.items()):
        if frac > Fraction(0):
            display = party_display_names.get(canonical_key, canonical_key)
            result.entries.append(OwnershipEntry(
                party=display,
                source_instrument=_last_instrument_for_party(canonical_key, eligible),
                source_document_id=_last_doc_id_for_party(canonical_key, eligible),
                interest_type="Royalty",
                interest_fraction=str(frac),
                interest_decimal=float(frac),
                section=section, township=township, range_=range_,
            ))

    for canonical_key, frac in sorted(wi_ledger.items()):
        if frac > Fraction(0):
            display = party_display_names.get(canonical_key, canonical_key)
            result.entries.append(OwnershipEntry(
                party=display,
                source_instrument=_last_instrument_for_party(canonical_key, eligible),
                source_document_id=_last_doc_id_for_party(canonical_key, eligible),
                interest_type="Working Interest",
                interest_fraction=str(frac),
                interest_decimal=float(frac),
                section=section, township=township, range_=range_,
                status="Open",
            ))

    # ── Verification sum ──────────────────────────────────────────────────
    fee_total = sum(fee_ledger.values(), Fraction(0))
    result.ledger_total_fraction = str(fee_total)
    if fee_total not in (Fraction(0), Fraction(1, 1)):
        result.exceptions.append(TitleException(
            source_document_id="",
            instrument="SUMMARY",
            grantor="",
            gap_description=(
                f"Fee interest sum = {fee_total} (expected 1). "
                "Review title chain for gaps or double-conveyances."
            ),
        ))
        logger.warning("Ownership sum check failed: %s", fee_total)

    return result


# ---------------------------------------------------------------------------
# Pipeline step
# ---------------------------------------------------------------------------

def run_ownership_analysis(
    records: list[SourceDocument],
    output_dir: str | Path,
    metadata: ProjectMetadata | dict[str, Any] | None = None,
) -> tuple[OwnershipResult, dict[str, Any]]:
    if isinstance(metadata, dict):
        metadata = ProjectMetadata(**metadata)

    section = (metadata.section or "") if metadata else ""
    township = (metadata.township or "") if metadata else ""
    range_ = (metadata.range or "") if metadata else ""

    try:
        result = build_ownership_ledger(
            records,
            section=section or None,
            township=township or None,
            range_=range_ or None,
        )
    except Exception as exc:
        logger.error("Ownership ledger build failed: %s", exc, exc_info=True)
        result = OwnershipResult()

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = output_dir / "ownership_entries.json"
    try:
        write_json(artifact_path, {
            "generated_at": timestamp(),
            "section": section,
            "township": township,
            "range": range_,
            "entries": [e.model_dump() for e in result.entries],
            "exceptions": [e.model_dump() for e in result.exceptions],
            "summary": result.as_dict(),
        })
    except Exception as exc:
        logger.warning("Could not write ownership_entries.json: %s", exc)

    metrics = result.as_dict()
    metrics["artifact"] = str(artifact_path)
    return result, metrics


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _move_interest(
    ledger: dict[str, Fraction],
    grantor_key: str,
    grantee_key: str,
    amount: Fraction,
) -> None:
    if amount <= Fraction(0):
        return
    new_grantor = ledger.get(grantor_key, Fraction(0)) - amount
    if new_grantor == Fraction(0):
        ledger.pop(grantor_key, None)
    else:
        ledger[grantor_key] = new_grantor
    ledger[grantee_key] = ledger.get(grantee_key, Fraction(0)) + amount


def _last_instrument_for_party(canonical_key: str, records: list[SourceDocument]) -> str:
    matches = [r for r in records if canonical_party_key(r.grantee or "") == canonical_key]
    return _instrument_ref(matches[-1]) if matches else ""


def _last_doc_id_for_party(canonical_key: str, records: list[SourceDocument]) -> str:
    matches = [r for r in records if canonical_party_key(r.grantee or "") == canonical_key]
    return matches[-1].source_document_id if matches else ""
