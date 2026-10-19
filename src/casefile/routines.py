"""Issue 14: the routine a Job runs on. The Coordinator plans from the
routine's domain pack; a Lot never falls back to a default."""
from __future__ import annotations

from typing import Any

ROUTINES: dict[str, dict[str, Any]] = {
    "cibola_surface": {
        "id": "cibola_surface", "pack": "title-texas-surface", "work_type": "surface_title",
        "label": "Cibola · surface title por tract (Texas)"},
    "emirates_minerals": {
        "id": "emirates_minerals", "pack": "title-texas-oil-gas-dd", "work_type": "oil_gas_dd",
        "label": "Emirates · minerals / due diligence de óleo e gás (Texas)"},
}
WORK_TYPES = frozenset(r["work_type"] for r in ROUTINES.values())


def get(routine: Any) -> dict[str, Any]:
    if routine not in ROUTINES:
        raise ValueError("job_routine_required")
    return ROUTINES[routine]
