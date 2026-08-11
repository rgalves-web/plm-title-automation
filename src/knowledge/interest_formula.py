"""Prose interest formulas -> exact Fractions. Never dropped, never guessed.

A title opinion states ownership as arithmetic in words:

    62.5% x 7/8 less (62.5% x 50% x 5%) less (62.5% x 4.5%)

The old failure mode was worse than a wrong number: the formula did not parse,
the newest opinion was skipped, and an OLDER opinion was silently adopted as the
basis (assessment gaps #5/#6). Nobody saw a wrong answer — they saw a plausible
one from the wrong document.

So this module has exactly two outcomes. Either it returns an exact `Fraction`
with the parse it used, or it returns a `Blocking` naming the fragment it could
not read. There is no third branch, and in particular there is no fallback to a
previous opinion: flow spec §2 rule 6.

The AI's job is to transcribe the words; this code does the arithmetic, in
`fractions.Fraction`, per CLAUDE.md invariant 2.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

_NUMBER = re.compile(r"""
    (?P<pct>\d+(?:\.\d+)?)\s*%                 # 62.5%
  | (?P<num>\d+(?:\.\d+)?)\s*/\s*(?P<den>\d+(?:\.\d+)?)   # 7/8
  | (?P<dec>\d*\.\d+|\d+)                      # 0.875 | 3
""", re.VERBOSE)

# "less", "minus", "subject to" all subtract; "plus" adds. "of" and "times"
# multiply, as does bare juxtaposition through "x".
_ADD_OPS = {"plus": 1, "and": 1}
_SUB_OPS = {"less": -1, "minus": -1}
_MUL_TOKENS = {"x", "*", "times", "of"}


@dataclass
class Blocking:
    """The formula could not be resolved. Adoption stops here."""
    formula: str
    reason: str
    fragment: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"formula": self.formula, "reason": self.reason,
                "fragment": self.fragment}


@dataclass
class Parsed:
    value: Fraction
    formula: str
    terms: list[tuple[int, Fraction, str]]      # (sign, value, source text)

    @property
    def decimal(self) -> str:
        return f"{float(self.value):.8f}"

    def to_dict(self) -> dict[str, Any]:
        return {"formula": self.formula, "value": str(self.value),
                "decimal": self.decimal,
                "terms": [{"sign": "+" if s > 0 else "-", "value": str(v),
                           "text": t} for s, v, t in self.terms]}


def parse_formula(text: str) -> Parsed | Blocking:
    """Evaluate a prose interest formula exactly, or refuse to."""
    raw = str(text or "").strip()
    if not raw:
        return Blocking(formula=raw, reason="formula_vazia")

    normalized = re.sub(r"\s+", " ", raw.replace("×", "x"))
    try:
        chunks = _split_terms(normalized)
    except ValueError as exc:
        return Blocking(formula=raw, reason="parenteses_desbalanceados",
                        fragment=str(exc))
    if not chunks:
        return Blocking(formula=raw, reason="nenhum_termo_reconhecido")

    total = Fraction(0)
    terms: list[tuple[int, Fraction, str]] = []
    for sign, chunk in chunks:
        value = _product(chunk)
        if value is None:
            return Blocking(formula=raw, reason="fator_ilegivel", fragment=chunk)
        total += sign * value
        terms.append((sign, value, chunk.strip()))
    return Parsed(value=total, formula=raw, terms=terms)


def _split_terms(text: str) -> list[tuple[int, str]]:
    """Split on top-level less/plus, respecting parentheses."""
    out: list[tuple[int, str]] = []
    depth = 0
    sign = 1
    buf: list[str] = []
    tokens = re.findall(r"\(|\)|[^()\s]+", text)
    for tok in tokens:
        if tok == "(":
            depth += 1
            buf.append(tok)
            continue
        if tok == ")":
            depth -= 1
            if depth < 0:
                raise ValueError(text)
            buf.append(tok)
            continue
        word = tok.lower().strip(",;")
        if depth == 0 and (word in _SUB_OPS or word in _ADD_OPS):
            if buf:
                out.append((sign, " ".join(buf)))
                buf = []
            sign = -1 if word in _SUB_OPS else 1
            continue
        buf.append(tok)
    if depth != 0:
        raise ValueError(text)
    if buf:
        out.append((sign, " ".join(buf)))
    return out


def _product(chunk: str) -> Fraction | None:
    """A term is a product of factors. Everything must be consumed."""
    body = chunk.strip()
    while body.startswith("(") and body.endswith(")") and _balanced(body[1:-1]):
        body = body[1:-1].strip()

    # A nested group inside a term is itself a formula (it may contain "less").
    if "(" in body:
        pieces, rest = [], body
        while "(" in rest:
            start = rest.index("(")
            end = _match_paren(rest, start)
            if end is None:
                return None
            head, inner, rest = rest[:start], rest[start + 1:end], rest[end + 1:]
            head_value = _plain_product(head)
            if head_value is None:
                return None
            inner_parsed = parse_formula(inner)
            if isinstance(inner_parsed, Blocking):
                return None
            pieces.append(head_value * inner_parsed.value)
        tail = _plain_product(rest)
        if tail is None:
            return None
        result = tail
        for piece in pieces:
            result *= piece
        return result

    return _plain_product(body)


def _plain_product(text: str) -> Fraction | None:
    """Factors with no parentheses. Empty text is the identity, not a failure."""
    result = Fraction(1)
    seen = False
    pos = 0
    body = text.strip()
    while pos < len(body):
        ch = body[pos]
        if ch.isspace():
            pos += 1
            continue
        m = _NUMBER.match(body, pos)
        if m:
            value = _to_fraction(m)
            if value is None:
                return None
            result *= value
            seen = True
            pos = m.end()
            continue
        word = re.match(r"[A-Za-z*]+", body[pos:])
        if word and word.group(0).lower() in _MUL_TOKENS:
            pos += word.end()
            continue
        return None            # an unrecognised token is a refusal, not a skip
    return result if seen else Fraction(1)


def _to_fraction(m: re.Match[str]) -> Fraction | None:
    try:
        if m.group("pct"):
            return Fraction(m.group("pct")) / 100
        if m.group("num"):
            den = Fraction(m.group("den"))
            if den == 0:
                return None
            return Fraction(m.group("num")) / den
        return Fraction(m.group("dec"))
    except (ValueError, ZeroDivisionError):
        return None


def _balanced(text: str) -> bool:
    depth = 0
    for ch in text:
        depth += (ch == "(") - (ch == ")")
        if depth < 0:
            return False
    return depth == 0


def _match_paren(text: str, start: int) -> int | None:
    depth = 0
    for i in range(start, len(text)):
        depth += (text[i] == "(") - (text[i] == ")")
        if depth == 0:
            return i
    return None
