"""Pending-reasons layer: no silent blanks (Maxwell lessons item 1).

A blank in a client-facing cell is information only if the reader knows WHY it is
blank. "No Pugh clause" and "we never found the document" look identical in the
workbook and mean opposite things. This module records, for every blank the
pipeline leaves, a machine-readable reason plus where to look to resolve it.

Two hard rules:
  * The reason lives in the AUDIT layer, never in the client cell. A client cell
    is blank or it holds a value — it never holds commentary.
  * Every blank the pipeline is responsible for must have a reason. The QA gate
    `every_blank_has_a_reason` fails the run otherwise, so a blank can never
    silently mean "we didn't get to it".

Reason semantics (the distinction the reader actually needs):
  pending_document           — we know exactly which instrument controls, it is
                               simply not in the file. Carries its identifier
                               (Vol/Page, contract no.) so it can be ordered.
  awaiting_reviewer_decision — a scope question only a human can answer.
  clause_absent              — the blank IS the information: the instrument has
                               no such clause (no Pugh, no depth severance).
  source_not_title           — the value exists outside the title chain
                               (e.g. RRC well data); not a title defect.
  unresolved_identity        — a party could not be tied to one identity.
  unresolved_fraction        — a fraction/formula would not resolve exactly.
  not_found                  — searched, genuinely absent.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class PendingReason(str, Enum):
    PENDING_DOCUMENT = "pending_document"
    AWAITING_REVIEWER_DECISION = "awaiting_reviewer_decision"
    CLAUSE_ABSENT = "clause_absent"
    SOURCE_NOT_TITLE = "source_not_title"
    UNRESOLVED_IDENTITY = "unresolved_identity"
    UNRESOLVED_FRACTION = "unresolved_fraction"
    NOT_FOUND = "not_found"

    def __str__(self) -> str:  # audit/report rendering
        return self.value


# A blank explained by one of these is EXPECTED and complete — it is not work
# left undone, so it never understates the deliverable.
_RESOLVED_REASONS = {PendingReason.CLAUSE_ABSENT, PendingReason.SOURCE_NOT_TITLE}


@dataclass(frozen=True)
class PendingItem:
    sheet: str
    location: str                 # cell coordinate or row reference
    field_name: str               # the column/field left blank
    reason: PendingReason
    where_to_look: str            # the specific next action for the reviewer
    identifier: str | None = None  # Vol/Page, contract no. — for pending_document

    @property
    def is_outstanding(self) -> bool:
        """True when the blank represents work still to be done."""
        return self.reason not in _RESOLVED_REASONS

    def describe(self) -> str:
        ident = f" [{self.identifier}]" if self.identifier else ""
        return (f"{self.sheet} · {self.location} · {self.field_name}: "
                f"{self.reason}{ident} — {self.where_to_look}")


class PendingRegistry:
    """Collects the pending items for one run."""

    def __init__(self) -> None:
        self.items: list[PendingItem] = []

    def add(self, sheet: str, location: str, field_name: str,
            reason: PendingReason | str, where_to_look: str,
            identifier: str | None = None) -> PendingItem:
        if not isinstance(reason, PendingReason):
            reason = PendingReason(str(reason))
        item = PendingItem(sheet, location, field_name, reason, where_to_look, identifier)
        self.items.append(item)
        return item

    def has(self, sheet: str, location: str, field_name: str) -> bool:
        return any(i.sheet == sheet and i.location == location and i.field_name == field_name
                   for i in self.items)

    @property
    def outstanding(self) -> list[PendingItem]:
        return [i for i in self.items if i.is_outstanding]

    def by_reason(self) -> dict[PendingReason, list[PendingItem]]:
        out: dict[PendingReason, list[PendingItem]] = {}
        for item in self.items:
            out.setdefault(item.reason, []).append(item)
        return out

    def audit_rows(self) -> list[tuple[str, str, str, str, None, str]]:
        """(sheet, location, source_type, source_reference, confidence, text)
        tuples for the DD_Audit_Trail — the reason never reaches a client cell."""
        return [
            (i.sheet, f"{i.location} ({i.field_name})", f"pending:{i.reason}",
             i.where_to_look, None,
             f"identifier: {i.identifier}" if i.identifier else "")
            for i in self.items
        ]

    def report_rows(self) -> list[list[str]]:
        """Rows for the 'Pending Items' report, most actionable first."""
        order = {r: n for n, r in enumerate(
            [PendingReason.PENDING_DOCUMENT, PendingReason.UNRESOLVED_IDENTITY,
             PendingReason.UNRESOLVED_FRACTION, PendingReason.AWAITING_REVIEWER_DECISION,
             PendingReason.NOT_FOUND, PendingReason.SOURCE_NOT_TITLE,
             PendingReason.CLAUSE_ABSENT])}
        rows = [["Sheet", "Location", "Field", "Reason", "Identifier", "Where to look"]]
        for i in sorted(self.items, key=lambda x: (order.get(x.reason, 99), x.sheet, x.location)):
            rows.append([i.sheet, i.location, i.field_name, str(i.reason),
                         i.identifier or "", i.where_to_look])
        return rows
