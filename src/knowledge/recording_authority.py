"""The one place that decides a recording. Every writer asks here.

Fifth instance of the same lesson, and the reason this module exists instead of
another patch: the fix belongs at the point of TRUTH, not at the point of error.

  PR-8 found the Lease Review carrying `Volume 199, Page 336` — the deed
  reference out of a lease's own land description — in the RECORDING column.
  The fix went into the Lease Review writer. It worked: that tab's trail still
  records "extraction read 'Volume 199, Page 336…' — not adopted".

  PR-10 wrote a Runsheet. Its writer never heard of the rule, so the same wrong
  string shipped again in `Runsheet!C5` and `C6`, contradicting the Lease Review
  in the same workbook. A gate that proves a source was cited cannot catch this:
  the citation was real, the field read from it was wrong.

So the rule is code, in one function, and a test asserts that every writer of a
recording field calls it. The authority is the unit designation's Exhibit "A"
(`knowledge/taxonomy/categories.yaml` → `dpu.authority`): it names the leases
that are in the unit and the volume/page each was recorded at. An extraction
that disagrees is recorded as not-adopted — visible, never silent, never used.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

AUTHORITY_NAME = 'unit designation, Exhibit "A"'


def normalise(value: Any) -> str:
    """Volume/page as a comparable key. `Vol. 567, Pg. 170` == `567.170`."""
    digits = re.findall(r"\d+", str(value or ""))
    return ".".join(digits[:2]) if len(digits) >= 2 else ""


@dataclass
class ResolvedRecording:
    value: str
    citation: str
    adopted_from: str            # "authority" | "extraction" | "none"
    rejected: str = ""           # what the extraction said, when it disagreed

    @property
    def book_page(self) -> tuple[str, str]:
        digits = re.findall(r"\d+", self.value)
        return (digits[0], digits[1]) if len(digits) >= 2 else ("", "")


class RecordingAuthority:
    """lease number -> the recording Exhibit "A" states for it."""

    def __init__(self, by_lease: dict[str, str]) -> None:
        self._by_lease = {str(k): str(v or "") for k, v in by_lease.items()}

    @classmethod
    def from_exhibit_a(cls, leases: dict[str, dict[str, Any]]) -> "RecordingAuthority":
        return cls({lease: spec.get("recording", "")
                    for lease, spec in leases.items()})

    def __len__(self) -> int:
        return len(self._by_lease)

    def known(self, lease: str) -> bool:
        return bool(self._by_lease.get(str(lease)))

    def resolve(self, lease: str, extracted: Any = None) -> ResolvedRecording:
        """The recording to write, and the citation that justifies it.

        The authority wins whenever it knows the lease. An extraction is used
        only where the authority is silent, and then it is cited as what it is."""
        authority = self._by_lease.get(str(lease), "")
        extracted_text = str(extracted or "").strip()
        if authority:
            if extracted_text and normalise(extracted_text) != normalise(authority):
                return ResolvedRecording(
                    value=authority,
                    citation=(f"{AUTHORITY_NAME} (extraction read "
                              f"{extracted_text[:48]!r} — not adopted)"),
                    adopted_from="authority", rejected=extracted_text)
            return ResolvedRecording(value=authority, citation=AUTHORITY_NAME,
                                     adopted_from="authority")
        if extracted_text:
            return ResolvedRecording(
                value=extracted_text,
                citation=("read from the instrument; Exhibit \"A\" does not "
                          "state a recording for this lease"),
                adopted_from="extraction")
        return ResolvedRecording(value="", citation="", adopted_from="none")


# Writers that must consult the authority. Named here so the test that enforces
# it fails loudly when a new tab is added without asking.
RECORDING_WRITERS = (
    ("src.knowledge.kit_builder", "write_ddr"),        # Lease Review column F
    ("src.knowledge.kit_builder", "write_runsheet"),   # Runsheet column C
    ("src.knowledge.ddr_tabs", "write_worksheet"),     # Worksheet columns K/L
)
