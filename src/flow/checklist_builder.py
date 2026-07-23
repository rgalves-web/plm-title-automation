"""Build the GATHER checklist from the manifest — the method, made explicit.

The checklist tells the analyst what to fetch, what it looks like, where to look,
and why it matters — so the process lives in the system, not in someone's memory
(blueprint §2, §4.3). Each item is DATA, not prose buried in code; per-``kind``
templates carry the reusable guidance and the manifest instantiates them.

Guidance strings encode the operational lessons the assessment names: county
searches are done by grantor/grantee name + date window, never by abstract; a
supplement controls, so an original is wanted-not-blocking; absence is declared,
not silently skipped.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Per-kind templates: the stable "what it looks like / why / where to look"
# guidance. ``blocking`` is the default; individual items may override it.
_TEMPLATES: dict[str, dict[str, Any]] = {
    "title_opinion": {
        "blocking": False,   # the latest cert date controls; an older one is wanted, not blocking
        "looks_like": "PDF whose first pages read TITLE OPINION / OPINION OF TITLE, "
                      "with a certification date; the newest cert date controls.",
        "where": ["Drive: the unit's title-opinion folder (files starting 'T-O' or the XREF number)"],
        "why": "The controlling opinion sets ownership; supplements amend it. "
               "A missing older opinion is declared, not blocking.",
    },
    "contract": {
        "blocking": True,
        "looks_like": "Recorded assignment / farmout / JOA package (zip named by K-number); "
                      "the operative instrument carries a '- REC' recording stamp.",
        "where": ["Drive: contract packages named 'K1400###'"],
        "why": "The recorded conveyance is the source for the seller's interest chain.",
    },
    "lease_folder": {
        "blocking": True,
        "looks_like": "Recorded oil-gas-mineral lease (and amendments) for the tract.",
        "where": ["Drive: lease folder for the lease number"],
        "why": "Lease terms (royalty, term, extensions) drive Lease Review.",
    },
    "dpu": {
        "blocking": True,
        "looks_like": "Declaration of Pooled Unit for THIS unit (+ any amendment), recorded.",
        "where": ["Drive: DPU package named by the unit's own contract number"],
        "why": "The DPU defines the unit; a foreign unit's DPU does not belong here.",
    },
    "runsheet_instrument": {
        "blocking": False,
        "looks_like": "County OPR capture of the recorded instrument showing the "
                      "grantor->EOG row with its document number and volume/page.",
        "where": ["County records site — search by GRANTOR/GRANTEE name + recording "
                  "date window, NEVER by abstract number."],
        "why": "Supplies the Title Documents; unlocatable rows are listed as MISSING.",
    },
    "rrc_report": {
        "blocking": False,
        "looks_like": "Texas RRC production/proration report for the subject well "
                      "(API), or the well's completion package.",
        "where": ["RRC online query by API or well name"],
        "why": "Populates Well Files; if absent it is reported MISSING, never substituted.",
    },
    "reference_workbook": {
        "blocking": True,
        "looks_like": "The unit's Project Log / Lease-to-Well XREF / Well List workbooks.",
        "where": ["Drive: unit reference folder"],
        "why": "The three reference workbooks seed the manifest and the WI/NRI baseline.",
    },
}

STATUS_PENDING = "pending"
STATUS_IN = "in"
STATUS_WAIVED = "waived"


@dataclass
class ChecklistItem:
    id: str
    kind: str
    what: str
    blocking: bool = True
    looks_like: str = ""
    where: list[str] = field(default_factory=list)
    why: str = ""
    status: str = STATUS_PENDING
    reason: str = ""            # required when status == waived

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "kind": self.kind, "what": self.what,
            "blocking": self.blocking, "looks_like": self.looks_like,
            "where": list(self.where), "why": self.why,
            "status": self.status, "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ChecklistItem":
        return cls(id=d["id"], kind=d["kind"], what=d["what"],
                   blocking=d.get("blocking", True), looks_like=d.get("looks_like", ""),
                   where=list(d.get("where", [])), why=d.get("why", ""),
                   status=d.get("status", STATUS_PENDING), reason=d.get("reason", ""))


def _item(kind: str, item_id: str, what: str, *, blocking: bool | None = None,
          where_extra: list[str] | None = None) -> ChecklistItem:
    tpl = _TEMPLATES[kind]
    where = list(tpl.get("where", []))
    if where_extra:
        where = where_extra + where
    return ChecklistItem(
        id=item_id, kind=kind, what=what,
        blocking=tpl["blocking"] if blocking is None else blocking,
        looks_like=tpl.get("looks_like", ""), where=where, why=tpl.get("why", ""),
    )


def build_checklist(manifest: dict[str, Any]) -> list[ChecklistItem]:
    """Instantiate the GATHER checklist from a manifest snapshot (a plain dict,
    as stored in the case file). Every title opinion, contract, lease, DPU, well
    and reference gap becomes a data-driven item with its own guidance."""
    items: list[ChecklistItem] = []

    for to in manifest.get("title_opinions", []):
        ref = str(to.get("file_number") or to.get("identifier") or "opinion")
        lessor = to.get("lessor")
        what = f"Title opinion — {lessor}" if lessor else f"Title opinion {ref}"
        items.append(_item("title_opinion", f"to_{ref}", what))

    for c in manifest.get("reference_contracts", []):
        ref = str(c.get("file_number") or "contract")
        rectype = c.get("record_type") or "contract"
        items.append(_item("contract", f"contract_{ref}", f"{rectype} — {ref}"))

    for lease in manifest.get("leases", []):
        no = str(lease.get("lease_no") or "lease")
        lessor = lease.get("lessor")
        what = f"Lease {no}" + (f" — {lessor}" if lessor else "")
        items.append(_item("lease_folder", f"lease_{no}", what))

    for well in manifest.get("wells", []):
        name = well.get("well_name") or "subject well"
        api = well.get("well_api")
        what = f"RRC production report — {name}" + (f" (API {api})" if api else "")
        items.append(_item("rrc_report", f"rrc_{name}", what))

    return items
