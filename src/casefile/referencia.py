"""Resolver de projeto, unit e workbooks de referência — por NOME, não caminho.

Extraído (cópia com adaptações mínimas) de src/dd/project_reference.py
(unit_folder, find_reference, date_in_filename, REFERENCE_PATTERNS,
describe_references) e src/dd/agreements_xref.py (unit_identity_tokens) — a
geração congelada não é editada nem reentra no caminho de decisão; só o
encanamento veio. Regra de sempre: a cópia autoritativa de cada referência
(XREF, Project Log, Well List, Schedule, template) vive na RAIZ do projeto do
cliente e é lida NO LUGAR — a versão mais nova pela data no próprio nome.
"""
from __future__ import annotations

import os
import re
from datetime import date
from pathlib import Path

DEFAULT_PROJECT_ROOT = Path(
    r"C:\Users\Renato\PURPLE LAND MGMT\BKV122TX - Project Emirates")

# Nomes datam-se de forma inconsistente: "06-16-2026", "6.9.26", "2026_07_09".
_DATE_PATTERNS = (
    re.compile(r"(?P<m>\d{1,2})[-_.](?P<d>\d{1,2})[-_.](?P<y>\d{4})"),
    re.compile(r"(?P<y>\d{4})[-_.](?P<m>\d{1,2})[-_.](?P<d>\d{1,2})"),
    re.compile(r"(?P<m>\d{1,2})[-_.](?P<d>\d{1,2})[-_.](?P<y>\d{2})\b"),
)

# Uma duplicata "Copy of ..." nunca vence o original.
_COPY_RE = re.compile(r"^\s*copy of\b", re.IGNORECASE)

REFERENCE_PATTERNS = {
    "xref": "*XREF*.xlsx",
    "project_log": "*Project Log*.xlsx",
    "well_list": "*Well List*.xlsx",
    "lease_mineral_schedule": "*Lease & Mineral Schedule*.xlsx",
    "ddr_template": "*DDR - Template*.xlsx",
}

_GENERIC_UNIT_TOKENS = {"UNIT", "THE", "A", "B", "C", "D", "AGREEMENT", "OF",
                        "POOLED", "DECL", "DECLARATION", "DEC"}


def raiz_do_projeto(override: str | Path | None = None) -> Path:
    if override:
        return Path(override)
    env = os.environ.get("CASEFILE_PROJECT_ROOT", "")
    return Path(env) if env else DEFAULT_PROJECT_ROOT


def date_in_filename(name: str) -> date | None:
    for pattern in _DATE_PATTERNS:
        match = pattern.search(name)
        if not match:
            continue
        year = int(match.group("y"))
        if year < 100:
            year += 2000
        try:
            return date(year, int(match.group("m")), int(match.group("d")))
        except ValueError:
            continue
    return None


def _rank(path: Path) -> tuple:
    parsed = date_in_filename(path.name)
    return (parsed is not None, parsed or date.min,
            not bool(_COPY_RE.match(path.name)), path.stat().st_mtime)


def find_reference(kind: str, project_root: Path | str | None = None
                   ) -> Path | None:
    """A cópia mais nova de uma referência na raiz do projeto; None quando
    ausente — quem chama expõe a ausência, nunca cai numa cópia velha."""
    if kind not in REFERENCE_PATTERNS:
        raise ValueError(f"referencia desconhecida {kind!r}; conhecidas: "
                         f"{sorted(REFERENCE_PATTERNS)}")
    root = raiz_do_projeto(project_root)
    if not root.exists():
        return None
    candidates = [p for p in root.glob(REFERENCE_PATTERNS[kind])
                  if p.is_file()]
    return max(candidates, key=_rank) if candidates else None


def unit_folder(unit_name: str, project_root: Path | str | None = None
                ) -> Path | None:
    """A pasta da unit sob a raiz — match case-insensitive, exato ou por
    tokens distintivos ("Josh B Unit" resolve "JOSH B UNIT"; "Cain Ranch A"
    resolve "CAIN RANCH A UNIT #1H WELL"). Ambiguidade devolve None — quem
    chama lista as candidatas e falha ruidosamente."""
    root = raiz_do_projeto(project_root)
    if not root.exists():
        return None
    target = unit_name.strip().upper()
    pastas = [c for c in root.iterdir() if c.is_dir()]
    for child in pastas:
        if child.name.strip().upper() == target:
            return child
    alvo = unit_identity_tokens(unit_name)
    if not alvo:
        return None
    por_tokens = [c for c in pastas
                  if alvo <= unit_identity_tokens(c.name)]
    return por_tokens[0] if len(por_tokens) == 1 else None


def listar_pastas_de_unit(project_root: Path | str | None = None
                          ) -> list[str]:
    root = raiz_do_projeto(project_root)
    if not root.exists():
        return []
    return sorted(c.name for c in root.iterdir() if c.is_dir())


def describe_references(project_root: Path | str | None = None
                        ) -> dict[str, str | None]:
    return {kind: (path.name if path else None)
            for kind, path in ((k, find_reference(k, project_root))
                               for k in REFERENCE_PATTERNS)}


def _tokens(text: str | None) -> set[str]:
    return {t for t in re.split(r"[^A-Z0-9]+", str(text or "").upper()) if t}


def unit_identity_tokens(unit_name: str | None) -> set[str]:
    """Os tokens distintivos de um nome de unit — "MAXWELL A UNIT" -> {"MAXWELL"}."""
    return _tokens(unit_name) - _GENERIC_UNIT_TOKENS
