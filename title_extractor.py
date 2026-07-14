"""Deterministic title extractor: OCR text -> template-grade conveyance + comments.
Backend-agnostic: rules layer here; an LLM backend can override per field later."""
from __future__ import annotations
import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Conveyance prefix by document type (mirrors Template MOR conventions)
# Matching is case-insensitive: normalise key before lookup.
# ---------------------------------------------------------------------------
CONVEYANCE_PREFIX: dict[str, str] = {
    # ── Patents ──────────────────────────────────────────────────────────────
    "patent": "Grant of:",

    # ── General deeds ────────────────────────────────────────────────────────
    "deed": "ARTI to:",
    "warranty deed": "ARTI to:",
    "special warranty deed": "ARTI to:",
    "joint tenancy warranty deed": "ARTI to:",
    "quit claim deed": "ARTI to:",
    "quitclaim deed": "ARTI to:",
    "gift deed": "ARTI to:",
    "mineral deed": "ARTI to:",
    "royalty deed": "ARTI to:",
    "tax deed": "ARTI to:",
    "correction deed": "ARTI to:",
    "corrected deed": "ARTI to:",
    "distribution deed": "ARTI to:",
    "personal representative deed": "ARTI to:",
    "public trustee's deed": "Grant of:",
    "public trustees deed": "Grant of:",
    "foreclosure deed": "Grant of:",
    "sheriff's deed": "Grant of:",
    "sheriffs deed": "Grant of:",
    "affidavit of heirship": "ARTI to:",
    "heirship affidavit": "ARTI to:",

    # ── Assignments / royalty ─────────────────────────────────────────────────
    "assignment": "Assignment of interest covering:",
    "correction assignment": "Correction of Assignment covering:",
    "assignment of royalty": "Assignment of royalty interest covering:",

    # ── Oil and Gas Leases ───────────────────────────────────────────────────
    "oil and gas lease": "Lease covering:",
    "oil & gas lease": "Lease covering:",
    "o&g lease": "Lease covering:",
    "lease": "Lease covering:",
    "oil and gas lease document": "Lease covering:",
    "o&g lease document": "Lease covering:",

    # OGL instruments
    "assignment of oil and gas lease": "Assignment of Lease covering:",
    "assignment of oil & gas lease": "Assignment of Lease covering:",
    "assignment of o&g lease": "Assignment of Lease covering:",
    "leasehold assignment": "Assignment of Lease covering:",

    "modification of oil and gas lease": "Modification of Lease covering:",
    "modification of oil & gas lease": "Modification of Lease covering:",
    "amendment of oil and gas lease": "Amendment of Lease covering:",

    "ratification of oil and gas lease": "Ratification of Lease covering:",
    "ratification of oil & gas lease": "Ratification of Lease covering:",

    "partial release of oil and gas lease": "Partial Release of Lease covering:",
    "partial release of oil & gas lease": "Partial Release of Lease covering:",

    "release of oil and gas lease": "Release of Lease covering:",
    "release of oil & gas lease": "Release of Lease covering:",

    "affidavit regarding oil and gas lease": "Affidavit regarding Lease covering:",
    "affidavit regarding oil & gas lease": "Affidavit regarding Lease covering:",
    "affidavit re oil and gas lease": "Affidavit regarding Lease covering:",

    # ── Pooling ──────────────────────────────────────────────────────────────
    "pooling agreement": "Pooling Agreement covering:",
    "pooling agreement amendment": "Amendment to Pooling Agreement covering:",
    "pooling agreement modification": "Amendment to Pooling Agreement covering:",

    # ── Probate / decrees ────────────────────────────────────────────────────
    "decree": "The Court orders, adjudicates and decrees title in:",
    "probate": "The Court orders, adjudicates and decrees title in:",
    "distribution by court": "The Court orders, adjudicates and decrees title in:",
    "quiet title": "The Court orders, adjudicates and decrees title in:",
    "decree of distribution": "The Court orders, adjudicates and decrees title in:",
    "decree affecting ownership": "The Court orders, adjudicates and decrees title in:",

    # ── Corrections ──────────────────────────────────────────────────────────
    "scrivener's affidavit": "Correction of:",
    "scriveners affidavit": "Correction of:",
}

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------
LEGAL_RE = re.compile(
    r"(?:township|twp\.?|t)\s*\d{1,3}\s*(?:south|north|[ns])"
    r"[^.\n]{0,120}?(?:range|rng\.?|r)\s*\d{1,3}\s*(?:east|west|[ew])"
    r"[^.\n]{0,160}", re.IGNORECASE)
SEC_RE = re.compile(r"section\s+\d{1,2}", re.IGNORECASE)
PRIMARY_TERM_RE = re.compile(
    r"primary\s+term\s+of\s+([a-z]+|\d{1,2})\s*\(?\d{0,2}\)?\s*years?", re.IGNORECASE)
TERM_YEARS_RE = re.compile(
    r"\bfor\s+a\s+(?:primary\s+)?term\s+of\s+([a-z]+|\d{1,2})\s*\(?(\d{0,2})\)?\s*years?", re.IGNORECASE)
ROYALTY_RE = re.compile(
    r"royalt(?:y|ies)[^.\n]{0,40}?(\d{1,2}\s*/\s*\d{1,2}|\d{1,2}(?:\.\d+)?\s*%|\d{1,2}\s*per\s*cent)",
    re.IGNORECASE)
RESERV_RE = re.compile(r"(reserv[a-z]*|excepts?|excepting)[^.\n]{0,120}", re.IGNORECASE)
ACRES_RE = re.compile(r"\b(\d{1,3}(?:\.\d+)?)\s+(?:more or less\s+)?acres?\b", re.IGNORECASE)
FRACTION_RE = re.compile(
    r"\b(?:an?\s+)?(?:undivided\s+)?(\d{1,3})\s*/\s*(\d{1,3})\s+(?:mineral\s+|royalty\s+|working\s+)?interest\b",
    re.IGNORECASE)

WORD_NUM = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "fifteen": 15, "twenty": 20,
}


@dataclass
class TitleFields:
    conveyance: str | None = None
    legal_description: str | None = None
    acreage: str | None = None
    comments: list[str] = field(default_factory=list)
    primary_term_years: int | None = None
    interest_fraction: str | None = None   # "1/2", "1/3", etc. if stated
    notes: list[str] = field(default_factory=list)


def _clean(t: str) -> str:
    return re.sub(r"\s+", " ", t).strip()


def _legal(text: str) -> str | None:
    m = LEGAL_RE.search(text)
    if m:
        return _clean(m.group(0))[:240]
    return None


def _primary_term(text: str) -> int | None:
    for rx in (PRIMARY_TERM_RE, TERM_YEARS_RE):
        m = rx.search(text)
        if m:
            g = m.group(1).lower()
            if g.isdigit():
                return int(g)
            if g in WORD_NUM:
                return WORD_NUM[g]
    return None


def _interest_fraction(text: str) -> str | None:
    """Return the first explicit fraction from the text (e.g. '1/2'), or None."""
    m = FRACTION_RE.search(text)
    if m:
        return f"{m.group(1)}/{m.group(2)}"
    return None


def _lookup_prefix(doc_type: str) -> str | None:
    """Case-insensitive prefix lookup; tries longest match first on multi-word types."""
    key = doc_type.strip().lower()
    return CONVEYANCE_PREFIX.get(key)


def extract(doc_type: str, ocr_text: str) -> TitleFields:
    text = ocr_text or ""
    compact = _clean(text)
    dt = (doc_type or "").strip().lower()
    tf = TitleFields()

    legal = _legal(compact)
    tf.legal_description = legal

    fraction = _interest_fraction(compact)
    tf.interest_fraction = fraction

    prefix = _lookup_prefix(dt)

    # Build conveyance: prefix + optional fraction prefix + legal description
    conv_parts: list[str] = []
    if prefix:
        if fraction and "interest" not in (prefix.lower()):
            # Insert fractional qualifier between prefix and legal
            conv_parts.append(f"an undivided {fraction} interest")
            if legal:
                conv_parts.append(legal)
            tf.conveyance = f"{prefix}\n\n" + "\n".join(conv_parts) if conv_parts else prefix
        elif legal:
            tf.conveyance = f"{prefix}\n\n{legal}"
        else:
            tf.conveyance = prefix
    elif legal:
        tf.conveyance = legal

    am = ACRES_RE.search(compact)
    if am:
        tf.acreage = am.group(1)

    # ── Title-analysis comments ──────────────────────────────────────────────
    is_ogl = any(k in dt for k in ("oil and gas lease", "oil & gas lease", "o&g lease", "lease"))

    if is_ogl:
        pt = _primary_term(compact)
        if pt:
            tf.primary_term_years = pt
            tf.comments.append(f"Primary Term: {pt} years")
        rm = ROYALTY_RE.search(compact)
        if rm:
            tf.comments.append(f"Royalty: {_clean(rm.group(1))}")

    rv = RESERV_RE.search(compact)
    if rv:
        snip = _clean(rv.group(0))[:140]
        tf.comments.append(f'RESERVATION/EXCEPTION: "{snip}"')

    return tf
