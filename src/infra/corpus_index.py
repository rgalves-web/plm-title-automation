"""Read the client corpus IN PLACE — the original zips, read-only, no copy.

The 2026-08-12 audit found `data/units/_josh_b_replay/corpus/`: a standing
duplicate of 1,105 client files that no step needed. The originals are zip
archives in the unit's `FILES/` folder; they are read-only by definition, so the
honest posture is to read them where they are and keep no second copy.

The round's state (classifications, dispositions) keys documents by the logical
path `<folder>/<member>` — the name inside the zip. This module resolves that
logical path back to its archive and reads the bytes straight from it. When a
step genuinely needs a real file on disk (a copy into the kit, a page render),
the member is materialised into the round's disposable `_work/` area at the
moment of use — scratch that can be deleted whole and re-derived from the zips.

Read-only is enforced, not assumed: this module exposes no write handle to the
source tree, and `materialise` refuses any destination outside `_work/`.
"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Any

WORK_DIRNAME = "_work"


class CorpusReadOnly(AssertionError):
    """An attempt to write into, or extract outside _work/ from, the corpus."""


class CorpusIndex:
    """logical path -> (zip file, member name), built once per source folder."""

    def __init__(self, files_dir: str | Path) -> None:
        self.files_dir = Path(files_dir)
        self._members: dict[str, tuple[Path, str]] = {}
        for archive in sorted(self.files_dir.glob("*.zip")):
            try:
                with zipfile.ZipFile(archive) as zf:
                    for member in zf.namelist():
                        if member.endswith("/"):
                            continue
                        self._members.setdefault(_norm(member), (archive, member))
            except zipfile.BadZipFile:
                continue
        # Loose files beside the zips are corpus too (the 4th title opinion
        # lived there). They are already in place; no zip indirection needed.
        for loose in self.files_dir.iterdir():
            if loose.is_file() and loose.suffix.lower() != ".zip":
                self._members.setdefault(_norm(loose.name), (loose, ""))

    def __len__(self) -> int:
        return len(self._members)

    def resolve(self, logical: str | Path) -> tuple[Path, str] | None:
        """Accepts a full old-corpus path or a bare `<folder>/<member>`."""
        text = str(logical).replace("\\", "/")
        if "/corpus/" in text:
            text = text.split("/corpus/", 1)[1]
        return self._members.get(_norm(text))

    def exists(self, logical: str | Path) -> bool:
        return self.resolve(logical) is not None

    def read_bytes(self, logical: str | Path) -> bytes:
        hit = self.resolve(logical)
        if hit is None:
            raise FileNotFoundError(f"not in the corpus index: {logical}")
        archive, member = hit
        if not member:                      # a loose file, already in place
            return archive.read_bytes()
        with zipfile.ZipFile(archive) as zf:
            return zf.read(member)

    def materialise(self, logical: str | Path, work_dir: str | Path) -> Path:
        """A real file for the steps that need one — inside _work/, nowhere else.

        The extraction is the disposable copy the old corpus/ folder pretended
        to be: it lives in scratch, is re-derived from the zip on demand, and
        deleting it loses nothing."""
        work_dir = Path(work_dir)
        if WORK_DIRNAME not in work_dir.parts:
            raise CorpusReadOnly(
                f"corpus members materialise only under {WORK_DIRNAME}/ — "
                f"{work_dir} would be a second standing copy of client data")
        hit = self.resolve(logical)
        if hit is None:
            raise FileNotFoundError(f"not in the corpus index: {logical}")
        archive, member = hit
        if not member:
            return archive                  # loose original: read it in place
        target = work_dir / "corpus" / member
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            with zipfile.ZipFile(archive) as zf:
                target.write_bytes(zf.read(member))
        return target


def _norm(member: str) -> str:
    text = re.sub(r"\s+", " ", str(member).replace("\\", "/")).strip().lower()
    return text
