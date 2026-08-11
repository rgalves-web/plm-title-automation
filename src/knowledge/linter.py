"""D3 — the knowledge linter: `knowledge/` must hold no unit fact.

The boundary between `knowledge/` (reusable) and `data/units/` (this case) is
the most important structural rule in the OKF. If a unit fact leaks into
knowledge, it poisons the next unit; if a rule stays trapped in a case, it is
lost. Prose cannot enforce that — this linter can, and it runs in the suite.

Scope (OKF plan D3): `ontology/`, `taxonomy/`, `rules/`, `lessons/global.yaml`
and `lessons/project/*` must be free of unit, lease, well and abstract
identifiers. `lessons/unit/*` is named quarantine and is exempt by design.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# Identifiers that name a specific case. Deliberately narrow and anchored:
# the linter must fire on real leakage, never on ordinary domain prose.
_UNIT_FACT_PATTERNS: dict[str, re.Pattern[str]] = {
    "lease number": re.compile(r"\b0\d{6}-\d{3}\b"),
    "contract number": re.compile(r"\bK1\d{6}\b"),
    "title opinion number": re.compile(r"\bT0\d{6}\b"),
    "API number": re.compile(r"\b\d{2}-\d{3}-\d{5}\b"),
    "recording reference": re.compile(r"\bVol\.?\s*\d{2,4}[,\s]+Pg\.?\s*\d{1,4}\b", re.I),
}

# Unit names seen in this engagement. A knowledge file naming one of them is
# describing a case, not a rule.
_UNIT_NAME_RE = re.compile(
    r"\b(BOWEN|MAXWELL|JOSH\s*B|ALAMO|CARNEGIE|WIESE|SIEBOLD)\b", re.IGNORECASE)

# Paths under knowledge/ where unit facts ARE allowed.
_EXEMPT_PARTS = ("lessons/unit/", "fixtures/")

# A line may cite a case as the ORIGIN of a rule ("learned on …") without the
# rule itself being case-specific. Such lines must say so explicitly.
_PROVENANCE_MARKERS = ("origin:", "source_event:", "learned_on:", "fixture:",
                       "# example", "# origin", "e.g.")


@dataclass(frozen=True)
class LintFinding:
    path: Path
    line_no: int
    kind: str
    text: str

    def describe(self) -> str:
        return (f"{self.path.as_posix()}:{self.line_no}: {self.kind} in knowledge/ "
                f"— unit facts belong in data/units/ — {self.text.strip()[:90]!r}")


def _is_exempt(path: Path, root: Path) -> bool:
    rel = path.relative_to(root).as_posix()
    return any(part in rel for part in _EXEMPT_PARTS)


def lint_knowledge(root: str | Path) -> list[LintFinding]:
    """Every unit fact found in the governed part of knowledge/."""
    root = Path(root)
    findings: list[LintFinding] = []
    for path in sorted(root.rglob("*.yaml")):
        if _is_exempt(path, root):
            continue
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if any(marker in line.lower() for marker in _PROVENANCE_MARKERS):
                continue                     # declared as provenance, not content
            for kind, pattern in _UNIT_FACT_PATTERNS.items():
                if pattern.search(line):
                    findings.append(LintFinding(path, line_no, kind, line))
            if _UNIT_NAME_RE.search(line):
                findings.append(LintFinding(path, line_no, "unit name", line))
    return findings
