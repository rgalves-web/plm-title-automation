"""The answer sheet is quarantined. A replay that reads it is not a replay.

`docs/JOSH_B_*` are the written record of what a human concluded by hand. They
are the thing the cold run is measured AGAINST, which makes them the one class
of file the run itself may never open. The comparison harness reads them, after
the run, from outside it.

This is not a style rule. Every number the replay reports — how many conclusions
it reproduced, how full the Lease Review is, which requirements it found — means
nothing if the run could have read the answers. And the failure mode is quiet:
nobody notices a `open(gabarito)` buried in a helper until the score stops being
evidence.

Usage: wrap the run.

    with quarantined():
        result = build_kit()

Anything under `docs/JOSH_B_*` opened inside the block raises `QuarantineBreach`.
"""
from __future__ import annotations

import builtins
import io
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

# The answer sheets. Patterns, not paths, because a fourth part of the gabarito
# would otherwise arrive unguarded.
QUARANTINED_PATTERNS: tuple[str, ...] = (
    r"docs[/\\]JOSH_B_.*",
    r".*[/\\]gabarito.*",
    # The delivered kit itself — the workbook a human filled in and submitted.
    # It is the answer sheet the cell-by-cell comparison measures against, and
    # it sits in the project folder beside the corpus the run legitimately
    # reads. Only the comparison harness opens it, from outside the run.
    r".*1\. Landman Submitted.*",
)
_PATTERNS = tuple(re.compile(p, re.IGNORECASE) for p in QUARANTINED_PATTERNS)


class QuarantineBreach(AssertionError):
    """The run opened the answer sheet. Its numbers are not evidence."""


def is_quarantined(path: Any) -> bool:
    text = str(path).replace("\\", "/")
    return any(p.search(text) for p in _PATTERNS)


@contextmanager
def quarantined(*, extra_patterns: tuple[str, ...] = ()) -> Iterator[list[str]]:
    """Fail loudly if the block opens an answer sheet. Yields the attempt log."""
    patterns = _PATTERNS + tuple(re.compile(p, re.IGNORECASE)
                                 for p in extra_patterns)

    def blocked(path: Any) -> bool:
        text = str(path).replace("\\", "/")
        return any(p.search(text) for p in patterns)

    attempts: list[str] = []
    real_open = builtins.open
    real_read_text = Path.read_text
    real_read_bytes = Path.read_bytes
    real_path_open = Path.open

    def guard(path: Any) -> None:
        if blocked(path):
            attempts.append(str(path))
            raise QuarantineBreach(
                f"the run tried to read the answer sheet: {path}\n"
                f"A replay that reads the gabarito is not a replay — its score "
                f"stops being evidence. Read it in the comparison harness, "
                f"after the run, outside this block.")

    def open_guarded(file, *args, **kwargs):            # noqa: ANN001
        guard(file)
        return real_open(file, *args, **kwargs)

    def read_text_guarded(self, *args, **kwargs):       # noqa: ANN001
        guard(self)
        return real_read_text(self, *args, **kwargs)

    def read_bytes_guarded(self, *args, **kwargs):      # noqa: ANN001
        guard(self)
        return real_read_bytes(self, *args, **kwargs)

    def path_open_guarded(self, *args, **kwargs):       # noqa: ANN001
        guard(self)
        return real_path_open(self, *args, **kwargs)

    builtins.open = open_guarded
    Path.read_text = read_text_guarded
    Path.read_bytes = read_bytes_guarded
    Path.open = path_open_guarded
    try:
        yield attempts
    finally:
        builtins.open = real_open
        Path.read_text = real_read_text
        Path.read_bytes = real_read_bytes
        Path.open = real_path_open
