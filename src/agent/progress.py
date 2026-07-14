"""Concise progress feed shared by the orchestrator and tools.

Mirrors the DD pipeline's ``progress_callback(icon, message)`` shape so a tool
can stream the same events it already emits. The log is collected in memory
(for tests / transcript) and optionally echoed through a sink (stdout in the
CLI)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass
class ProgressLog:
    sink: Callable[[str, str], None] | None = None
    events: list[tuple[str, str]] = field(default_factory=list)

    def __call__(self, icon: str, message: str) -> None:
        self.events.append((icon, message))
        if self.sink:
            self.sink(icon, message)

    def lines(self) -> list[str]:
        return [f"[{icon}] {msg}" for icon, msg in self.events]
