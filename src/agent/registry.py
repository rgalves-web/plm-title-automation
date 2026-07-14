"""Tool registry for the conversational shell.

A tool is a named, described, callable adapter with a small parameter schema.
Tools wrap the existing deterministic pipelines — they never reimplement them.
The registry is the only place the orchestrator learns what work it can do, so
selection is explicit and testable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

# A tool receives a params dict + a progress callback and returns a normalized
# result dict: {"status": "done"|"failed", "summary": str, "artifacts": [paths],
# "output_dir": str|None, "error": str|None, ...}.
ToolFn = Callable[[dict[str, Any], "Callable[[str, str], None] | None"], dict[str, Any]]


@dataclass
class Tool:
    name: str
    description: str
    run: ToolFn
    param_schema: dict[str, str] = field(default_factory=dict)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        if name not in self._tools:
            raise KeyError(f"No such tool: {name!r}. Registered: {sorted(self._tools)}")
        return self._tools[name]

    def has(self, name: str) -> bool:
        return name in self._tools

    def names(self) -> list[str]:
        return sorted(self._tools)

    def list(self) -> list[Tool]:
        return [self._tools[n] for n in self.names()]


def default_registry() -> ToolRegistry:
    """The registry wired to the real MOR and DD pipeline wrappers."""
    from src.agent.tools.mor_tool import MOR_TOOL
    from src.agent.tools.dd_tool import DD_TOOL

    reg = ToolRegistry()
    reg.register(MOR_TOOL)
    reg.register(DD_TOOL)
    return reg
