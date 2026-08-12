"""The page cache — global, keyed by what the page IS.

The old cache lived inside the unit's folder, so unit 200 paid again for a page
unit 1 had already read. The same assignment `K1400170` was bought three times
across three units. A cache keyed by page bytes has no reason to be per-unit:
the same bytes give the same answer whoever is asking.

It stores transformations of a page (its text layer, its OCR, its rendered
pixels), never a judgement about it. Judgements belong to the model and are
re-made; page bytes are facts and are paid for once.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

# Outside any unit folder, deliberately. Overridable so tests do not write to
# the real one.
DEFAULT_ROOT = Path("data/_page_cache")


def cache_root() -> Path:
    return Path(os.environ.get("PLM_PAGE_CACHE", str(DEFAULT_ROOT)))


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:32]


def key_for(*parts: Any) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")
                          ).hexdigest()[:32]


class PageCache:
    """Content-addressed store. Two shelves: text answers and raw bytes."""

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root) if root is not None else cache_root()
        self.hits = 0
        self.misses = 0

    def _path(self, key: str, suffix: str) -> Path:
        # Two-level fan-out: a flat directory of a hundred thousand pages is a
        # directory nobody can list.
        return self.root / key[:2] / f"{key}{suffix}"

    def get_text(self, key: str) -> str | None:
        path = self._path(key, ".json")
        if not path.exists():
            self.misses += 1
            return None
        self.hits += 1
        return json.loads(path.read_text(encoding="utf-8"))["text"]

    def put_text(self, key: str, text: str, meta: dict[str, Any] | None = None) -> None:
        path = self._path(key, ".json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"text": text, **(meta or {})}),
                        encoding="utf-8")

    def get_bytes(self, key: str) -> bytes | None:
        path = self._path(key, ".bin")
        if not path.exists():
            self.misses += 1
            return None
        self.hits += 1
        return path.read_bytes()

    def put_bytes(self, key: str, data: bytes) -> None:
        path = self._path(key, ".bin")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def stats(self) -> dict[str, int]:
        return {"hits": self.hits, "misses": self.misses}
