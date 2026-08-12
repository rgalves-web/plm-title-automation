"""Declared write-roots: a round says where it will write BEFORE it writes.

The repo audit of 2026-08-12 found what the absence of this rule produces:
scratch json strewn across `data/units/` root, a test workbook beside the
deliverables, twenty-six `state.v*.yaml` in a unit's root, and a full duplicate
of 1,105 client files that no step needed — the original corpus is read-only by
definition, so it is read in place.

The rule (CLAUDE.md invariant 26) has three parts:

  DECLARE FIRST. A round opens a `WriteScope` naming its roots. A write outside
  them raises — an exception, not a warning, because a warning is a log line
  nobody reads until the next audit.

  MANIFEST AFTER. The scope emits `write_manifest.json` listing every path
  written, so "where did this round write?" is a file, not a filesystem
  archaeology session.

  SCRATCH IS DISPOSABLE. Anything transient lives under `<root>/_work/`, which
  can be deleted whole without losing a deliverable. A scratch file that would
  hurt to delete is not scratch — it is an undeclared deliverable.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

WORK_DIRNAME = "_work"
MANIFEST_NAME = "write_manifest.json"


class WriteOutsideRoots(AssertionError):
    """A write landed outside the roots the round declared."""


@dataclass
class WriteScope:
    roots: list[Path]
    written: list[str] = field(default_factory=list)
    label: str = ""

    def check(self, path: str | Path) -> Path:
        """Assert the path is inside a declared root, and record it."""
        resolved = Path(path).resolve()
        for root in self.roots:
            try:
                resolved.relative_to(root)
                break
            except ValueError:
                continue
        else:
            raise WriteOutsideRoots(
                f"write outside the declared roots: {resolved}\n"
                f"declared: {[str(r) for r in self.roots]}\n"
                f"Declare the root before the round starts, or the file does "
                f"not get written. Scratch belongs under <root>/{WORK_DIRNAME}/.")
        if str(resolved) not in self.written:
            self.written.append(str(resolved))
        return resolved

    def work_dir(self, root: Path | None = None) -> Path:
        """The disposable scratch area. Deletable whole, by design."""
        base = Path(root) if root is not None else self.roots[0]
        work = base / WORK_DIRNAME
        work.mkdir(parents=True, exist_ok=True)
        return work

    def manifest(self) -> dict[str, Any]:
        return {"label": self.label,
                "roots": [str(r) for r in self.roots],
                "written": sorted(self.written),
                "count": len(self.written)}

    def write_manifest(self) -> Path:
        path = self.roots[0] / MANIFEST_NAME
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.manifest(), indent=1,
                                   ensure_ascii=False), encoding="utf-8")
        if str(path.resolve()) not in self.written:
            self.written.append(str(path.resolve()))
        return path


_ACTIVE: list[WriteScope] = []


def active_scope() -> WriteScope | None:
    return _ACTIVE[-1] if _ACTIVE else None


def record_write(path: str | Path) -> Path:
    """Called by every write helper. Outside a scope it only resolves; inside
    one it asserts and records."""
    scope = active_scope()
    if scope is None:
        return Path(path).resolve()
    return scope.check(path)


@contextmanager
def write_scope(*roots: str | Path, label: str = "") -> Iterator[WriteScope]:
    """Declare where this round is allowed to write. Emits the manifest on exit
    — including on failure, because a crashed round's writes matter MORE."""
    resolved = [Path(r).resolve() for r in roots]
    if not resolved:
        raise ValueError("a write scope needs at least one root")
    for r in resolved:
        r.mkdir(parents=True, exist_ok=True)
    scope = WriteScope(roots=resolved, label=label)
    _ACTIVE.append(scope)
    try:
        yield scope
    finally:
        _ACTIVE.pop()
        scope.write_manifest()
