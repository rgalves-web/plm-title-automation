"""Triage — decide what to read, and never skip blind.

The cost of a round is decided here: deep OCR of everything is unaffordable, so
the corpus is cut before it is read. But a cut made on filenames alone is the
regex decision this project abolished, so D4 holds: **every proposed SKIP is
confirmed by a first-page peek** — one cheap look — before it counts. Only two
things may skip without any look at all, because they are facts and not guesses:
a byte-identical duplicate, and a non-document file.

Everything is counted. N inventoried, N peeked, N deep-read, N skipped by
reason — no silent ceiling, no unexplained shrinkage.
"""
from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

READ = "read"
SKIP = "skip"
PEEK_NEEDED = "peek_needed"

# Extensions that are not documents at all. Skipping these needs no look.
_NON_DOCUMENT = {".ini", ".db", ".lnk", ".tmp", ".url", ".ds_store"}
_DOCUMENT = {".pdf", ".tif", ".tiff", ".png", ".jpg", ".jpeg",
             ".xlsx", ".xlsm", ".csv", ".doc", ".docx", ".txt"}


class TriageError(RuntimeError):
    """A skip was recorded without the look D4 requires."""


@dataclass
class TriageEntry:
    path: Path
    sha256: str
    size: int
    disposition: str = PEEK_NEEDED
    reason: str = ""                 # from the closed vocabulary
    peeked: bool = False
    peek_quote: str = ""             # what the first page actually said
    duplicate_of: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"file": self.path.name, "sha256": self.sha256, "size": self.size,
                "disposition": self.disposition, "reason": self.reason,
                "peeked": self.peeked, "peek_quote": self.peek_quote[:200],
                "duplicate_of": self.duplicate_of}


@dataclass
class TriageResult:
    entries: list[TriageEntry] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        """The accounting the plan demands — every file lands somewhere."""
        return {
            "inventoried": len(self.entries),
            "peeked": sum(1 for e in self.entries if e.peeked),
            "read": sum(1 for e in self.entries if e.disposition == READ),
            "skipped": sum(1 for e in self.entries if e.disposition == SKIP),
        }

    def skips_by_reason(self) -> dict[str, int]:
        return dict(Counter(e.reason for e in self.entries
                            if e.disposition == SKIP))

    def to_read(self) -> list[TriageEntry]:
        return [e for e in self.entries if e.disposition == READ]

    def unaccounted(self) -> list[TriageEntry]:
        """Anything still undecided — must be empty before a round closes."""
        return [e for e in self.entries if e.disposition == PEEK_NEEDED]

    def assert_no_blind_skip(self) -> None:
        """D4: every SKIP was either peeked or justified by strong metadata."""
        blind = [e for e in self.entries
                 if e.disposition == SKIP and not e.peeked
                 and e.reason not in ("duplicata", "fora_do_tipo")]
        if blind:
            raise TriageError(
                "skips recorded without a first-page peek: "
                + ", ".join(e.path.name for e in blind))


def _digest(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def inventory(root: str | Path) -> list[TriageEntry]:
    """Every file, with its hash. Nothing is excluded at this stage — you cannot
    count what you never listed."""
    root = Path(root)
    entries: list[TriageEntry] = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        entries.append(TriageEntry(path=path, sha256=_digest(path),
                                   size=path.stat().st_size))
    return entries


def triage(root: str | Path, perimeter: Any = None,
           peek: Callable[[Path], str] | None = None,
           knowledge: Any = None) -> TriageResult:
    """Inventory, then propose, then CONFIRM every proposed skip by peeking.

    peek(path) -> the first page's text. Injected, so the caller decides how
    cheap the look is (vision call, OCR of page 1, cached text). Without a peek
    function nothing may be skipped on suspicion — the entry stays PEEK_NEEDED
    and the round cannot close, which is the honest failure."""
    result = TriageResult(entries=inventory(root))
    seen_hashes: dict[str, TriageEntry] = {}

    for entry in result.entries:
        suffix = entry.path.suffix.lower()

        # --- strong metadata: skippable without a look --------------------
        if suffix in _NON_DOCUMENT or suffix not in _DOCUMENT:
            entry.disposition, entry.reason = SKIP, "fora_do_tipo"
            continue
        first = seen_hashes.get(entry.sha256)
        if first is not None:
            entry.disposition, entry.reason = SKIP, "duplicata"
            entry.duplicate_of = first.path.name
            continue
        seen_hashes[entry.sha256] = entry

        # --- a filename may only PROPOSE ----------------------------------
        proposed_reason = None
        if perimeter is not None:
            proposed_reason = perimeter.outside_reason(entry.path.name)

        if proposed_reason is None:
            entry.disposition = READ
            continue

        # --- D4: the proposal must survive a look -------------------------
        if peek is None:
            entry.disposition = PEEK_NEEDED
            entry.reason = proposed_reason
            continue
        text = peek(entry.path) or ""
        entry.peeked, entry.peek_quote = True, text[:200]
        confirmed = perimeter.outside_reason(text) if text.strip() else None
        if text.strip() and confirmed is None:
            # The content contradicts the filename: it belongs after all.
            entry.disposition, entry.reason = READ, ""
        else:
            entry.disposition, entry.reason = SKIP, proposed_reason
    return result


def negative_knowledge(result: TriageResult, perimeter: Any = None) -> list[str]:
    """What the brief must carry as `already_searched` (spec §6).

    Every skip the system proved is a search the operator must not repeat."""
    notes: list[str] = []
    by_reason = result.skips_by_reason()
    if by_reason.get("fora_do_perimetro"):
        labels = ", ".join(perimeter.abstract_labels()) if perimeter else "the unit perimeter"
        notes.append(
            f"{by_reason['fora_do_perimetro']} file(s) excluded as outside "
            f"{labels} — confirmed by first-page peek, do not re-search them")
    if by_reason.get("duplicata"):
        notes.append(f"{by_reason['duplicata']} byte-identical duplicate(s) already classified")
    return notes
