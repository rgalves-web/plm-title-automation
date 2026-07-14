"""Deterministic Fraction-based unit aggregation and WI/NRI reconciliation.

The LLM (title_opinion_parser) only transcribes fraction text; ALL arithmetic
happens here, in fractions.Fraction, never float — mirrors the discipline in
src/ownership.py. Float conversion happens only at the openpyxl-write
boundary in ddr_writer.py, never inside this module.

Mirrors the DDR template's own formula shapes (Ownership Report row 8+):
  company_net_acres        = tract_gross_acres * mi_value * wi_value   (R*S*T)
  nri_value                 = 1 - royalty - orri_burdens                (1-G-W)
  company_net_revenue_acres = company_net_acres * nri_value             (U*V)
  seller_wi  = company_net_acres_total / unit_gross_acres
  seller_nri = company_net_revenue_acres_total / unit_gross_acres
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from fractions import Fraction

from src.dd.manifest import UnitManifest
from src.schemas import QAException
from src.utils import get_logger

logger = get_logger(__name__)

# 0.0005, expressed exactly as a Fraction so the tolerance comparison is exact.
DD_RECONCILIATION_TOLERANCE = Fraction(5, 10000)

class AggregationError(RuntimeError):
    pass


# Tokenizer for interest-fraction expressions as printed in title opinions:
# numbers/fractions/percents combined with x-multiplication, "plus" addition,
# "less"/"minus" subtraction, and ()/[] grouping — e.g.
# "[(1/2 x 1/4) plus (1/2 x 1/9 x 1/4)]", "62.5% x 7/8 less (62.5% x 4.5%)".
_EXPR_TOKEN_RE = re.compile(
    r"""\s*(?:
          (?P<lpar>[\(\[])
        | (?P<rpar>[\)\]])
        | (?P<mul>x\b|×|of\b|times\b)
        | (?P<add>plus\b|\+)
        | (?P<sub>less\b|minus\b)
        | (?P<number>(?:\d+(?:\.\d+)?|\.\d+)(?:\s*/\s*(?:\d+(?:\.\d+)?|\.\d+))?\s*%?)
    )""",
    re.IGNORECASE | re.VERBOSE,
)


def _tokenize_fraction_expr(text: str) -> list[tuple[str, str]] | None:
    """Full-coverage tokenization; any unrecognized character means the text
    is prose, not an expression -> None (never guess)."""
    tokens: list[tuple[str, str]] = []
    pos = 0
    while pos < len(text):
        match = _EXPR_TOKEN_RE.match(text, pos)
        if not match:
            return None if text[pos:].strip() else tokens
        pos = match.end()
        for kind in ("lpar", "rpar", "mul", "add", "sub", "number"):
            value = match.group(kind)
            if value is not None:
                tokens.append((kind, value))
                break
    return tokens


def _number_token_value(raw: str) -> Fraction | None:
    raw = raw.strip()
    is_percent = raw.endswith("%")
    if is_percent:
        raw = raw[:-1].strip()
    try:
        if "/" in raw:
            numerator_text, denominator_text = (p.strip() for p in raw.split("/", 1))
            value = Fraction(numerator_text) / Fraction(denominator_text)
        else:
            value = Fraction(raw)
    except (ValueError, ZeroDivisionError):
        return None
    return value / 100 if is_percent else value


def _parse_term(tokens: list[tuple[str, str]], pos: int) -> tuple[Fraction | None, int]:
    value, pos = _parse_factor(tokens, pos)
    if value is None:
        return None, pos
    while pos < len(tokens) and tokens[pos][0] == "mul":
        right, pos = _parse_factor(tokens, pos + 1)
        if right is None:
            return None, pos
        value *= right
    return value, pos


def _parse_factor(tokens: list[tuple[str, str]], pos: int) -> tuple[Fraction | None, int]:
    if pos >= len(tokens):
        return None, pos
    kind, raw = tokens[pos]
    if kind == "number":
        return _number_token_value(raw), pos + 1
    if kind == "lpar":
        value, pos = _parse_expr(tokens, pos + 1)
        if value is None or pos >= len(tokens) or tokens[pos][0] != "rpar":
            return None, pos
        return value, pos + 1
    return None, pos


def _parse_expr(tokens: list[tuple[str, str]], pos: int) -> tuple[Fraction | None, int]:
    value, pos = _parse_term(tokens, pos)
    if value is None:
        return None, pos
    while pos < len(tokens) and tokens[pos][0] in ("add", "sub"):
        op = tokens[pos][0]
        right, pos = _parse_term(tokens, pos + 1)
        if right is None:
            return None, pos
        value = value + right if op == "add" else value - right
    return value, pos


def derive_wi_from_nri_formula(
    formula_text: str | None,
    stated_nri: Fraction | None,
) -> Fraction | None:
    """Recover the WORKING interest from a NET-REVENUE calculation formula.

    Title opinion WI tables print, per company, the NRI calculation whose
    terms are (working-interest component x revenue factor), e.g. EOG's
    "[(49.768518% x 4/5) plus (35.185186% x 75%)]" — the working interest is
    the sum of each term's leading factors (49.768518% + 35.185186% =
    .84953704) and the full product sum is the NRI (.66203704).

    Guarded strictly, never a guess:
      - the text must parse as a top-level SUM of flat products of plain
        numbers (no nesting, no subtraction);
      - every term needs >= 2 factors and a final factor < 1 (a revenue
        factor; dropping the only factor would fabricate "All");
      - when stated_nri is provided, the full formula value must CHECKSUM
        against it (tolerance 1e-6) — proof the text is the NRI calculation;
      - the derived WI must exceed the formula's NRI value and be <= 1.
    Returns None if any check fails.
    """
    if not formula_text:
        return None
    tokens = _tokenize_fraction_expr(str(formula_text).split("=")[0].strip())
    if not tokens:
        return None

    # Strip one optional outer bracket pair enclosing the whole expression.
    if tokens[0][0] == "lpar" and tokens[-1][0] == "rpar":
        depth = 0
        wraps_all = True
        for index, (kind, _raw) in enumerate(tokens):
            if kind == "lpar":
                depth += 1
            elif kind == "rpar":
                depth -= 1
                if depth == 0 and index != len(tokens) - 1:
                    wraps_all = False
                    break
        if wraps_all:
            tokens = tokens[1:-1]

    # Split into top-level terms on ADD (any SUB disqualifies).
    terms: list[list[Fraction]] = []
    factors: list[Fraction] = []
    expect_number = True
    depth = 0
    for kind, raw in tokens:
        if kind == "lpar":
            depth += 1
            if depth > 1:
                return None  # nested structure — not a flat product
        elif kind == "rpar":
            depth -= 1
            if depth < 0:
                return None
        elif kind == "sub":
            return None
        elif kind == "add":
            if depth != 0 or not factors:
                return None
            terms.append(factors)
            factors = []
            expect_number = True
        elif kind == "mul":
            if expect_number:
                return None
            expect_number = True
        elif kind == "number":
            if not expect_number:
                return None
            value = _number_token_value(raw)
            if value is None:
                return None
            factors.append(value)
            expect_number = False
    if depth != 0 or not factors:
        return None
    terms.append(factors)

    if any(len(term) < 2 for term in terms):
        return None
    if any(term[-1] >= 1 for term in terms):
        return None

    nri_value = Fraction(0)
    wi_value = Fraction(0)
    for term in terms:
        product = Fraction(1)
        for factor in term:
            product *= factor
        nri_value += product
        wi_value += product / term[-1]

    if stated_nri is not None and abs(nri_value - stated_nri) > Fraction(1, 10**6):
        return None
    if not (nri_value < wi_value <= 1):
        return None
    return wi_value


def parse_fraction_text(text: str | None) -> Fraction | None:
    """Parse fraction text exactly as printed in a title opinion or template
    cell, always in exact Fraction arithmetic (never via float).

    Handles plain fractions ("1/2"), decimal strings ("0.6250000"), percents
    ("62.5%"), the literal word "All" (full interest), x-multiplication chains
    ("1/2 x 1/8"), and bracketed sum/difference formulas as opinions print
    them ("[(1/2 x 1/4) plus (1/2 x 1/9 x 1/4)]",
    "62.5% x 7/8 less (62.5% x 4.5%)"). Returns None — never a guess — for
    prose, unbalanced brackets, division by zero, or a negative result.
    """
    if not text:
        return None
    text = str(text).strip()
    if not text:
        return None

    text_before_eq = text.split("=")[0].strip()
    if text_before_eq.upper().rstrip(".") == "ALL":
        return Fraction(1, 1)

    tokens = _tokenize_fraction_expr(text_before_eq)
    if not tokens:
        return None
    value, pos = _parse_expr(tokens, 0)
    if value is None:
        return None
    # Opinions often restate a formula's decimal image right after it, e.g.
    # "(1/4) .25000000" or "(25% x 1/2) .12500000" — the trailing number is a
    # checksum, not a factor. Accept it only when it AGREES with the computed
    # expression (return the exact Fraction); a mismatch means the text was
    # garbled in transcription and we refuse rather than pick a side.
    if pos == len(tokens) - 1 and tokens[pos][0] == "number":
        stated = _number_token_value(tokens[pos][1])
        if stated is not None and abs(value - stated) <= Fraction(1, 10**6):
            pos += 1
    if pos != len(tokens) or value < 0:
        return None
    return value


@dataclass
class LeaseTractRow:
    lease_no: str
    tract_gross_acres: Fraction
    mi_value: Fraction
    wi_value: Fraction
    royalty: Fraction
    orri_burdens: Fraction = Fraction(0)

    @property
    def company_net_acres(self) -> Fraction:
        return self.tract_gross_acres * self.mi_value * self.wi_value

    @property
    def nri_value(self) -> Fraction:
        return Fraction(1) - self.royalty - self.orri_burdens

    @property
    def company_net_revenue_acres(self) -> Fraction:
        return self.company_net_acres * self.nri_value


@dataclass
class AggregationResult:
    unit_gross_acres: Fraction
    company_net_acres_total: Fraction
    company_net_revenue_acres_total: Fraction
    seller_wi: Fraction
    seller_nri: Fraction
    rows: list[LeaseTractRow] = field(default_factory=list)


@dataclass
class ReconciliationResult:
    computed_wi: Fraction
    computed_nri: Fraction
    represented_wi: Fraction
    represented_nri: Fraction
    wi_delta: Fraction
    nri_delta: Fraction
    wi_status: str
    nri_status: str


def aggregate_unit(
    unit_gross_acres: str | Fraction,
    rows: list[LeaseTractRow],
) -> AggregationResult:
    gross = (
        unit_gross_acres
        if isinstance(unit_gross_acres, Fraction)
        else Fraction(str(unit_gross_acres))
    )
    if gross <= 0:
        raise AggregationError("unit_gross_acres must be a positive value.")

    net_acres_total = sum((r.company_net_acres for r in rows), Fraction(0))
    net_revenue_acres_total = sum((r.company_net_revenue_acres for r in rows), Fraction(0))

    return AggregationResult(
        unit_gross_acres=gross,
        company_net_acres_total=net_acres_total,
        company_net_revenue_acres_total=net_revenue_acres_total,
        seller_wi=net_acres_total / gross,
        seller_nri=net_revenue_acres_total / gross,
        rows=rows,
    )


def reconcile(
    aggregation: AggregationResult,
    represented_wi: str,
    represented_nri: str,
) -> ReconciliationResult:
    rep_wi = Fraction(str(represented_wi))
    rep_nri = Fraction(str(represented_nri))

    wi_delta = abs(aggregation.seller_wi - rep_wi)
    nri_delta = abs(aggregation.seller_nri - rep_nri)

    return ReconciliationResult(
        computed_wi=aggregation.seller_wi,
        computed_nri=aggregation.seller_nri,
        represented_wi=rep_wi,
        represented_nri=rep_nri,
        wi_delta=wi_delta,
        nri_delta=nri_delta,
        wi_status="WARNING" if wi_delta > DD_RECONCILIATION_TOLERANCE else "PASS",
        nri_status="WARNING" if nri_delta > DD_RECONCILIATION_TOLERANCE else "PASS",
    )


def reconciliation_qa_exceptions(reconciliation: ReconciliationResult) -> list[QAException]:
    """Never returns ERROR severity — reconciliation is informational only."""
    exceptions: list[QAException] = []
    if reconciliation.wi_status == "WARNING":
        exceptions.append(
            QAException(
                severity="WARNING",
                code="DD_WI_RECONCILIATION",
                message=(
                    f"Computed Seller WI {float(reconciliation.computed_wi):.7f} vs represented "
                    f"{float(reconciliation.represented_wi):.7f}, delta "
                    f"{float(reconciliation.wi_delta):.7f} exceeds tolerance "
                    f"{float(DD_RECONCILIATION_TOLERANCE):.4f}."
                ),
                field="seller_wi",
            )
        )
    if reconciliation.nri_status == "WARNING":
        exceptions.append(
            QAException(
                severity="WARNING",
                code="DD_NRI_RECONCILIATION",
                message=(
                    f"Computed Seller NRI {float(reconciliation.computed_nri):.7f} vs represented "
                    f"{float(reconciliation.represented_nri):.7f}, delta "
                    f"{float(reconciliation.nri_delta):.7f} exceeds tolerance "
                    f"{float(DD_RECONCILIATION_TOLERANCE):.4f}."
                ),
                field="seller_nri",
            )
        )
    return exceptions


def run_dd_aggregation(
    manifest: UnitManifest,
    rows: list[LeaseTractRow],
) -> tuple[AggregationResult, ReconciliationResult, list[QAException]]:
    if not manifest.unit_gross_acres:
        raise AggregationError(
            f"manifest.unit_gross_acres is not set for unit '{manifest.unit_name}'. "
            "This is a manual field — fill it in manifest.yaml before running aggregation."
        )
    if not manifest.represented_interest:
        raise AggregationError(
            f"manifest.represented_interest is not set for unit '{manifest.unit_name}'."
        )

    aggregation = aggregate_unit(manifest.unit_gross_acres, rows)

    represented = manifest.represented_interest
    if represented.basis != "leasehold":
        # The aggregate is a LEASEHOLD interest; the represented figure (Well
        # List) is a WELLBORE interest that legitimately includes non-consent/
        # JOA uplift. Delta-comparing the two would manufacture a defect out
        # of a basis difference, so the comparison is N/A — both figures are
        # still carried for side-by-side display, and no QA warning is raised.
        reconciliation = ReconciliationResult(
            computed_wi=aggregation.seller_wi,
            computed_nri=aggregation.seller_nri,
            represented_wi=Fraction(str(represented.current_wi)),
            represented_nri=Fraction(str(represented.current_nri)),
            wi_delta=Fraction(0),
            nri_delta=Fraction(0),
            wi_status="N/A",
            nri_status="N/A",
        )
        return aggregation, reconciliation, []

    reconciliation = reconcile(
        aggregation,
        represented.current_wi,
        represented.current_nri,
    )
    exceptions = reconciliation_qa_exceptions(reconciliation)
    return aggregation, reconciliation, exceptions
