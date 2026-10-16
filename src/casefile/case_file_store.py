"""Write-once Case File store: Function files under the Case folder (ADR 0001).

Every Function input and output file for a Case lands at

    <operation root>/casos/<unit_id>/_casefile/<stage>/<function>/<task>/<name>

beside a write-once metadata record at `<task>/.meta/<name>.json` holding its
sha256, size, write time and, optionally, the earlier Case file it supersedes
and why. A path is written once: any second write to it is refused with a
named error, never replaced. Corrections are new files that name the file
they supersede, so the history of a Case can be followed by opening files.

Superseding a file first creates `.meta/<name>.superseded_by` beside it,
no-clobber, before any byte of the new file: of two concurrent superseders
exactly one claims the marker and the other fails at once with
`CaseFileAlreadySuperseded`, so a supersession chain never forks.

Builds on the declared operation root and atomic writes in `storage.py`
(`case_root`, `create_once`, `digest_file`) and on the pen's write-roots
(`record_write`): a write outside the Case folder, or outside a declared
write scope, is refused before any byte is written.

Plumbing only. Nothing here reads, judges or compares the content of a file.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.casefile import storage
from src.casefile.estados import ESTADOS
from src.knowledge.write_roots import record_write

CASEFILE_DIR = "_casefile"
META_DIR = ".meta"
SCHEMA = 1

# The ten Functions, by the code names the operation already uses
# (operations.ROLE_NAMES); a test keeps the two lists in step.
FUNCTIONS = ("coordenador", "pesquisador", "arquivista", "classificador",
             "examinador", "verificador", "arbitro", "redator", "qa_pacote",
             "retrospectivo")

_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL",
                     *(f"COM{n}" for n in range(1, 10)),
                     *(f"LPT{n}" for n in range(1, 10))}


# --- named errors ------------------------------------------------------------

class CaseFileError(ValueError):
    """Base of every refusal of the Case File store."""
    code = "case_file_error"


class CaseFileInvalidSegment(CaseFileError):
    code = "case_file_invalid_segment"


class CaseFileUnknownStage(CaseFileError):
    code = "case_file_unknown_stage"


class CaseFileUnknownFunction(CaseFileError):
    code = "case_file_unknown_function"


class CaseFileOutsideCase(CaseFileError):
    code = "case_file_outside_case"


class CaseFileAlreadyWritten(CaseFileError):
    """A second write to a path that already holds a Case file."""
    code = "case_file_already_written"

    def __init__(self, relative: str, existing_sha256: str | None,
                 attempted_sha256: str) -> None:
        self.relative = relative
        self.existing_sha256 = existing_sha256
        self.attempted_sha256 = attempted_sha256
        self.same_content = existing_sha256 == attempted_sha256
        super().__init__(
            f"{self.code}: {relative} is already written "
            f"(existing sha256 {str(existing_sha256)[:12]}, attempted "
            f"{attempted_sha256[:12]}); Case files are never replaced — "
            f"write a new file that supersedes it")


class CaseFileNotFound(CaseFileError):
    code = "case_file_not_found"


class CaseFileIncomplete(CaseFileError):
    """Metadata exists but the file does not: an interrupted write."""
    code = "case_file_incomplete"


class CaseFileTampered(CaseFileError):
    """The bytes on disk no longer match the recorded sha256."""
    code = "case_file_tampered"


class CaseFileSupersessionWithoutReason(CaseFileError):
    code = "case_file_supersession_without_reason"


class CaseFileAlreadySuperseded(CaseFileError):
    code = "case_file_already_superseded"


class CaseFileSupersessionBroken(CaseFileError):
    """A recorded supersession no longer points at the bytes it named."""
    code = "case_file_supersession_broken"


# --- the record --------------------------------------------------------------

@dataclass(frozen=True)
class CaseFileRecord:
    unit_id: int
    stage: str
    function: str
    task: str
    name: str
    relative: str
    path: Path
    sha256: str
    size: int
    written_at: str
    supersedes: str | None = None
    supersedes_sha256: str | None = None
    reason: str = ""

    def meta(self) -> dict[str, Any]:
        return {"schema": SCHEMA, "unit_id": self.unit_id,
                "stage": self.stage, "function": self.function,
                "task": self.task, "name": self.name,
                "relative": self.relative, "sha256": self.sha256,
                "size": self.size, "written_at": self.written_at,
                "supersedes": self.supersedes,
                "supersedes_sha256": self.supersedes_sha256,
                "reason": self.reason}


# --- paths -------------------------------------------------------------------

def casefile_root(unit_id: int) -> Path:
    """`<operation root>/casos/<unit_id>/_casefile` — the only write root."""
    return storage.case_root(unit_id) / CASEFILE_DIR


def _segment(kind: str, value: Any) -> str:
    text = str(value)
    if not _SEGMENT.match(text) or text.split(".")[0].upper() in \
            _WINDOWS_RESERVED:
        raise CaseFileInvalidSegment(
            f"case_file_invalid_segment: {kind} {text!r} must be one plain "
            f"path segment (letters, digits, '.', '_', '-'; no separators, "
            f"no leading dot, no reserved device name)")
    return text


def _stage(value: Any) -> str:
    text = str(value).strip().upper()
    if text not in ESTADOS:
        raise CaseFileUnknownStage(
            f"case_file_unknown_stage: {value!r}; Stages: {list(ESTADOS)}")
    return text.lower()


def _function(value: Any) -> str:
    text = str(value).strip().lower()
    if text not in FUNCTIONS:
        raise CaseFileUnknownFunction(
            f"case_file_unknown_function: {value!r}; Functions: "
            f"{list(FUNCTIONS)}")
    return text


def _inside(root: Path, target: Path) -> Path:
    resolved_root = root.resolve()
    resolved = target.resolve()
    if resolved == resolved_root or not resolved.is_relative_to(
            resolved_root):
        raise CaseFileOutsideCase(
            f"case_file_outside_case: {target} is not inside {resolved_root}")
    return resolved


def _parts(relative: str | Path | CaseFileRecord
           ) -> tuple[str, str, str, str]:
    if isinstance(relative, CaseFileRecord):
        relative = relative.relative
    pieces = str(relative).replace("\\", "/").split("/")
    if len(pieces) != 4:
        raise CaseFileInvalidSegment(
            f"case_file_invalid_segment: {relative!r} must be "
            f"<stage>/<function>/<task>/<name>")
    stage, function, task, name = pieces
    return (_stage(stage), _function(function), _segment("task", task),
            _segment("name", name))


def _locate(unit_id: int, stage: str, function: str, task: str, name: str
            ) -> tuple[str, Path, Path]:
    root = casefile_root(unit_id)
    relative = f"{stage}/{function}/{task}/{name}"
    folder = root / stage / function / task
    target = _inside(root, folder / name)
    meta = _inside(root, folder / META_DIR / f"{name}.json")
    return relative, target, meta


# --- reading -----------------------------------------------------------------

def _record_from_meta(unit_id: int, path: Path, meta_path: Path
                      ) -> CaseFileRecord:
    meta = json.loads(meta_path.read_text("utf-8"))
    return CaseFileRecord(
        unit_id=int(unit_id), stage=meta["stage"], function=meta["function"],
        task=meta["task"], name=meta["name"], relative=meta["relative"],
        path=path, sha256=meta["sha256"], size=meta["size"],
        written_at=meta["written_at"], supersedes=meta.get("supersedes"),
        supersedes_sha256=meta.get("supersedes_sha256"),
        reason=meta.get("reason", ""))


def read(unit_id: int, relative: str | Path | CaseFileRecord
         ) -> CaseFileRecord:
    """The record of a written Case file, after checking its bytes still
    hash to the recorded sha256."""
    relative_text, target, meta = _locate(unit_id, *_parts(relative))
    if not meta.exists():
        raise CaseFileNotFound(
            f"case_file_not_found: {relative_text} in case {unit_id}")
    if not target.exists():
        raise CaseFileIncomplete(
            f"case_file_incomplete: {relative_text} has metadata but no "
            f"file (interrupted write)")
    record = _record_from_meta(unit_id, target, meta)
    actual = storage.digest_file(target)
    if actual != record.sha256:
        raise CaseFileTampered(
            f"case_file_tampered: {relative_text} hashes to {actual[:12]} "
            f"but was written as {record.sha256[:12]}")
    return record


def read_bytes(unit_id: int, relative: str | Path | CaseFileRecord) -> bytes:
    record = read(unit_id, relative)
    data = record.path.read_bytes()
    if hashlib.sha256(data).hexdigest() != record.sha256:
        raise CaseFileTampered(
            f"case_file_tampered: {record.relative} changed while reading")
    return data


def records(unit_id: int) -> list[CaseFileRecord]:
    """Every Case file with metadata, in path order (no content checks)."""
    root = casefile_root(unit_id)
    if not root.exists():
        return []
    out = []
    for meta in sorted(root.glob(f"*/*/*/{META_DIR}/*.json")):
        target = meta.parent.parent / meta.name[:-len(".json")]
        out.append(_record_from_meta(unit_id, target, meta))
    return out


def _marker_path(unit_id: int, stage: str, function: str, task: str,
                 name: str) -> Path:
    """`<task>/.meta/<name>.superseded_by`: the write-once claim that the
    file `name` has been superseded, and by what."""
    root = casefile_root(unit_id)
    return _inside(root, root / stage / function / task / META_DIR
                   / f"{name}.superseded_by")


def superseded_by(unit_id: int, relative: str | Path | CaseFileRecord
                  ) -> list[CaseFileRecord]:
    """The Case file that supersedes `relative` ([] if none), read through
    its supersession marker and checked against what the marker claims."""
    marker = _marker_path(unit_id, *_parts(relative))
    if not marker.exists():
        return []
    claim = json.loads(marker.read_text("utf-8"))
    try:
        later = read(unit_id, claim["by"])
    except (CaseFileNotFound, CaseFileIncomplete):
        raise CaseFileIncomplete(
            f"case_file_incomplete: {claim['superseded']} is claimed by "
            f"{claim['by']}, which was not fully written (interrupted "
            f"write; repeating that same write completes it)") from None
    if later.sha256 != claim["by_sha256"] or \
            later.supersedes != claim["superseded"] or \
            later.supersedes_sha256 != claim["superseded_sha256"]:
        raise CaseFileSupersessionBroken(
            f"case_file_supersession_broken: the marker of "
            f"{claim['superseded']} does not match {later.relative}")
    return [later]


def chain(unit_id: int, relative: str | Path | CaseFileRecord
          ) -> list[CaseFileRecord]:
    """From `relative` back to the original: [it, what it superseded, ...].
    Each link is checked against the sha256 it recorded."""
    out = [read(unit_id, relative)]
    while out[-1].supersedes:
        previous = read(unit_id, out[-1].supersedes)
        if previous.sha256 != out[-1].supersedes_sha256:
            raise CaseFileSupersessionBroken(
                f"case_file_supersession_broken: {out[-1].relative} "
                f"superseded {previous.relative} at sha256 "
                f"{str(out[-1].supersedes_sha256)[:12]}, now "
                f"{previous.sha256[:12]}")
        out.append(previous)
    return out


def latest(unit_id: int, relative: str | Path | CaseFileRecord
           ) -> CaseFileRecord:
    """The newest file in the supersession chain that starts at `relative`."""
    current = read(unit_id, relative)
    while True:
        later = superseded_by(unit_id, current)
        if not later:
            return current
        current = later[0]


# --- writing -----------------------------------------------------------------

def write(unit_id: int, *, stage: str, function: str, task: str | int,
          name: str, data: bytes,
          supersedes: str | Path | CaseFileRecord | None = None,
          reason: str = "") -> CaseFileRecord:
    """Write a Function file for a Case, once.

    Refuses, before writing anything: a bad segment, an unknown Stage or
    Function, a target outside the Case folder or outside a declared write
    scope, a supersession without a reason, of an unknown or changed file, or
    of a file already superseded. Refuses after: a path already written
    (`CaseFileAlreadyWritten`, carrying both hashes)."""
    if not isinstance(data, (bytes, bytearray)):
        raise TypeError("data must be bytes")
    data = bytes(data)
    parts = (_stage(stage), _function(function), _segment("task", task),
             _segment("name", name))
    relative, target, meta_path = _locate(unit_id, *parts)
    # The pen: a declared write scope that does not cover this Case refuses
    # the write here, before any byte lands.
    record_write(target)
    record_write(meta_path)

    sha = hashlib.sha256(data).hexdigest()
    if target.exists():
        existing = (_record_from_meta(unit_id, target, meta_path).sha256
                    if meta_path.exists() else storage.digest_file(target))
        raise CaseFileAlreadyWritten(relative, existing, sha)

    earlier = marker = None
    supersedes_relative = supersedes_sha = None
    if supersedes is not None:
        if not str(reason or "").strip():
            raise CaseFileSupersessionWithoutReason(
                "case_file_supersession_without_reason: a file that "
                "supersedes another must say why")
        earlier = read(unit_id, supersedes)
        if earlier.relative == relative:
            raise CaseFileAlreadyWritten(relative, earlier.sha256, sha)
        marker = _marker_path(unit_id, earlier.stage, earlier.function,
                              earlier.task, earlier.name)
        record_write(marker)
        supersedes_relative, supersedes_sha = earlier.relative, earlier.sha256

    record = CaseFileRecord(
        unit_id=int(unit_id), stage=parts[0], function=parts[1],
        task=parts[2], name=parts[3], relative=relative, path=target,
        sha256=sha, size=len(data),
        written_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        supersedes=supersedes_relative, supersedes_sha256=supersedes_sha,
        reason=str(reason or "").strip() if supersedes is not None else "")

    # Claim the supersession BEFORE writing anything of the new file: the
    # marker is created with no-clobber semantics, so of two concurrent
    # superseders exactly one wins and the other fails here, having written
    # nothing. Only the same write (same target, bytes and reason) may pass
    # an existing marker, to complete itself after an interruption.
    if marker is not None:
        claim = {"schema": SCHEMA, "superseded": earlier.relative,
                 "superseded_sha256": earlier.sha256, "by": relative,
                 "by_sha256": sha, "reason": record.reason}
        try:
            storage.create_once(marker, json.dumps(
                claim, ensure_ascii=False, sort_keys=True,
                indent=1).encode("utf-8"))
        except FileExistsError:
            prior = json.loads(marker.read_text("utf-8"))
            if prior != claim:
                raise CaseFileAlreadySuperseded(
                    f"case_file_already_superseded: {earlier.relative} is "
                    f"already superseded by {prior.get('by')}") from None

    # Metadata first, then the file. The file's presence is what "written"
    # means; metadata without its file is an interrupted write, which the
    # SAME write (same content, same supersession) may complete.
    try:
        storage.create_once(meta_path, _meta_bytes(record))
    except FileExistsError:
        prior = _record_from_meta(unit_id, target, meta_path)
        if not _same_intent(prior, record):
            raise CaseFileAlreadyWritten(relative, prior.sha256, sha)
        record = prior
    try:
        storage.create_once(target, data)
    except FileExistsError:
        raise CaseFileAlreadyWritten(relative, storage.digest_file(target),
                                     sha)
    return record


def _meta_bytes(record: CaseFileRecord) -> bytes:
    return json.dumps(record.meta(), ensure_ascii=False, sort_keys=True,
                      indent=1).encode("utf-8")


def _same_intent(prior: CaseFileRecord, attempt: CaseFileRecord) -> bool:
    keys = ("relative", "sha256", "size", "supersedes", "supersedes_sha256",
            "reason")
    return all(getattr(prior, k) == getattr(attempt, k) for k in keys)
