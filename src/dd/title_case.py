"""Deterministic Title Case normalization for DDR client-facing text.

Title opinions and the XREF arrive ALL CAPS; the DDR should read in Title Case
while preserving entity forms (LLC, LP, Inc.), name suffixes (Jr., III), estate
role words (Trustee), and legal references (survey abstracts like A-122,
volume/page). All rules are config-driven (config/title_case_exceptions.yaml) —
no LLM, no hidden logic. This is a formatting pass only; it never changes a
number, fraction, date, or the meaning of a value.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml

_CONFIG = Path("config/title_case_exceptions.yaml")


@lru_cache(maxsize=4)
def _load(config_path: str = str(_CONFIG)) -> tuple[dict[str, str], tuple[re.Pattern, ...]]:
    data = yaml.safe_load(Path(config_path).read_text(encoding="utf-8")) or {}
    exact: dict[str, str] = {}
    for entry in data.get("exact", []) or []:
        if "->" in str(entry):
            key, val = (s.strip() for s in str(entry).split("->", 1))
        else:
            key = val = str(entry).strip()
        exact[key.upper()] = val
    patterns = tuple(re.compile(p) for p in (data.get("preserve_patterns", []) or []))
    return exact, patterns


_WORD_RE = re.compile(r"[A-Za-z0-9&.\-/']+|\s+|[^\sA-Za-z0-9&.\-/']")


def _title_token(token: str) -> str:
    # Hyphenated/scoped names: title-case each alpha segment, keep separators.
    parts = re.split(r"([\-/'.])", token)
    out = []
    for part in parts:
        if part in ("-", "/", "'", ".") or not part:
            out.append(part)
        elif part.isdigit():
            out.append(part)
        else:
            out.append(part[:1].upper() + part[1:].lower())
    return "".join(out)


def to_title_case(text: str | None, config_path: str = str(_CONFIG)) -> str | None:
    """Return *text* in Title Case with configured exceptions preserved. Only
    normalizes strings that are effectively all-caps (leaves already-cased text
    and non-text untouched), so re-running is idempotent and mixed-case analyst
    input is respected."""
    if text is None:
        return None
    s = str(text)
    if not s.strip():
        return s
    letters = [c for c in s if c.isalpha()]
    if letters and any(c.islower() for c in letters):
        return s  # already has lowercase — respect existing casing

    exact, patterns = _load(config_path)

    # Mask preserve-patterns so their casing survives verbatim.
    masked: list[str] = []
    def _mask(m: re.Match) -> str:
        masked.append(m.group(0))
        return f"\x00{len(masked) - 1}\x00"
    work = s
    for pat in patterns:
        work = pat.sub(_mask, work)

    def _convert(m: re.Match) -> str:
        tok = m.group(0)
        if tok.isspace() or "\x00" in tok:
            return tok
        if not any(c.isalpha() for c in tok):
            return tok
        if tok.upper() in exact:
            return exact[tok.upper()]
        return _title_token(tok)

    result = _WORD_RE.sub(_convert, work)
    # Restore masked patterns.
    result = re.sub(r"\x00(\d+)\x00", lambda m: masked[int(m.group(1))], result)
    return result
