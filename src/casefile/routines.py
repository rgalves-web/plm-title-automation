"""Issue 14: the routine a Job runs on. The Coordinator plans from the
routine's domain pack; a Lot never falls back to a default.

Issue 17: each routine also lists the Job's sources with how they are
reached. A Lot's envelope is every one of them; RRC is never one (Renato's
standing rule: it charges the company).

- public: the Researcher reaches it with no operator;
- network: public, but this machine may need a network the operator provides;
- login: an account or credential the operator holds;
- paid: every search or document costs money.
"""
from __future__ import annotations

from typing import Any

_SOURCES: dict[str, dict[str, str]] = {
    "local": {"label": "Acervo local", "access": "public"},
    "glo": {"label": "Texas GLO · land grants e PDFs públicos", "access": "public"},
    "topics": {"label": "TOPICs · citações e notices judiciais", "access": "public"},
    "terrell_cad": {"label": "Terrell CAD · cartão fiscal", "access": "network"},
    "countyrecords": {"label": "CountyRecords · índice e prévias do County Clerk", "access": "login"},
    "texasfile": {"label": "TexasFile · índice grantor/grantee", "access": "login"},
    "drive": {"label": "Google Drive · pasta do projeto", "access": "login"},
    "courthousedirect": {"label": "CourthouseDirect · pesquisa e cópias", "access": "paid"},
    "pacer": {"label": "PACER · tribunais federais", "access": "paid"},
    "sosdirect": {"label": "SOSDirect · entidades (Texas SOS)", "access": "paid"},
}
FORBIDDEN_SOURCES = frozenset({"rrc"})

ROUTINES: dict[str, dict[str, Any]] = {
    "cibola_surface": {
        "id": "cibola_surface", "pack": "title-texas-surface", "work_type": "surface_title",
        "label": "Cibola · surface title por tract (Texas)",
        "sources": ["local", "glo", "topics", "terrell_cad", "countyrecords", "texasfile",
                    "drive", "courthousedirect", "pacer", "sosdirect"]},
    "emirates_minerals": {
        "id": "emirates_minerals", "pack": "title-texas-oil-gas-dd", "work_type": "oil_gas_dd",
        "label": "Emirates · minerals / due diligence de óleo e gás (Texas)",
        "sources": ["local", "glo", "topics", "texasfile", "drive", "courthousedirect",
                    "pacer", "sosdirect"]},
}
WORK_TYPES = frozenset(r["work_type"] for r in ROUTINES.values())
SOURCE_KEYS = frozenset(_SOURCES)


def get(routine: Any) -> dict[str, Any]:
    if routine not in ROUTINES:
        raise ValueError("job_routine_required")
    return ROUTINES[routine]


def job_sources(routine: Any) -> list[str]:
    return list(get(routine)["sources"])


def access(source: str) -> str:
    return _SOURCES.get(source, {}).get("access", "public")


def label(source: str) -> str:
    return _SOURCES.get(source, {}).get("label", source)


def catalog(routine: Any) -> list[dict[str, str]]:
    return [{"source": s, **_SOURCES[s]} for s in job_sources(routine)]
