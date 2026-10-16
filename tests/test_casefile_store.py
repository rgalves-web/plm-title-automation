"""Write-once Case File store (issue 01, ADR 0001) — plumbing only.

Nothing here asserts a title conclusion: the bytes are synthetic and the
tests prove placement, hashing, write-once refusal, supersession chains and
the pen's write-roots.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from src.casefile import case_file_store as store
from src.casefile import storage
from src.knowledge.write_roots import WriteOutsideRoots, write_scope

UNIT = 7


@pytest.fixture(autouse=True)
def operation_root(tmp_path, monkeypatch):
    root = tmp_path / "OPERATIONS"
    monkeypatch.setenv("PLM_OPERATION_ROOT", str(root))
    return root


def _write(name="output.json", data=b'{"synthetic": 1}', task="42",
           stage="EXAMINANDO", function="examinador", unit=UNIT, **kw):
    return store.write(unit, stage=stage, function=function, task=task,
                       name=name, data=data, **kw)


# --- placement and hash ------------------------------------------------------

def test_write_lands_under_case_by_stage_function_task_with_sha(
        operation_root):
    record = _write()
    expected = (operation_root / "casos" / str(UNIT) / "_casefile"
                / "examinando" / "examinador" / "42" / "output.json")
    assert record.path == expected.resolve()
    assert expected.read_bytes() == b'{"synthetic": 1}'
    assert record.relative == "examinando/examinador/42/output.json"
    assert record.sha256 == hashlib.sha256(b'{"synthetic": 1}').hexdigest()
    meta = json.loads((expected.parent / ".meta" / "output.json.json")
                      .read_text("utf-8"))
    assert meta["sha256"] == record.sha256 and meta["size"] == 16
    assert store.read(UNIT, record.relative) == record


def test_no_temporary_files_left_behind(operation_root):
    record = _write()
    leftovers = [p for p in record.path.parent.rglob("*")
                 if p.name.endswith(".tmp")]
    assert leftovers == []


# --- write-once --------------------------------------------------------------

def test_second_write_to_same_path_is_refused_never_replaced():
    first = _write(data=b"first")
    with pytest.raises(store.CaseFileAlreadyWritten) as other:
        _write(data=b"second")
    assert other.value.code == "case_file_already_written"
    assert other.value.existing_sha256 == first.sha256
    assert not other.value.same_content
    with pytest.raises(store.CaseFileAlreadyWritten) as same:
        _write(data=b"first")            # identical bytes are refused too
    assert same.value.same_content       # but the caller can tell
    assert first.path.read_bytes() == b"first"


def test_create_once_never_clobbers(tmp_path):
    target = tmp_path / "x.bin"
    storage.create_once(target, b"a")
    with pytest.raises(FileExistsError):
        storage.create_once(target, b"b")
    assert target.read_bytes() == b"a"
    assert [p.name for p in tmp_path.iterdir()] == ["x.bin"]


def test_interrupted_write_is_completed_only_by_the_same_write(
        operation_root):
    record = _write(name="input.json", data=b"same")
    record.path.unlink()                  # simulate: meta landed, file did not
    with pytest.raises(store.CaseFileIncomplete):
        store.read(UNIT, record.relative)
    with pytest.raises(store.CaseFileAlreadyWritten):
        _write(name="input.json", data=b"different")
    completed = _write(name="input.json", data=b"same")
    assert completed.sha256 == record.sha256
    assert store.read_bytes(UNIT, record.relative) == b"same"


def test_tampered_file_is_refused_on_read():
    record = _write(data=b"original")
    record.path.chmod(0o666)
    record.path.write_bytes(b"edited by hand")
    with pytest.raises(store.CaseFileTampered):
        store.read(UNIT, record.relative)


# --- supersession ------------------------------------------------------------

def test_supersession_chain_reads_back_without_touching_the_original():
    first = _write(task="1", data=b"v1")
    second = _write(task="2", data=b"v2", supersedes=first,
                    reason="synthetic correction")
    third = _write(task="3", data=b"v3", supersedes=second.relative,
                   reason="second synthetic correction")
    assert [r.relative for r in store.chain(UNIT, third)] == \
        [third.relative, second.relative, first.relative]
    assert third.supersedes_sha256 == second.sha256
    assert [r.relative for r in store.superseded_by(UNIT, first)] == \
        [second.relative]
    assert store.latest(UNIT, first).relative == third.relative
    assert first.path.read_bytes() == b"v1"
    assert store.read(UNIT, first).sha256 == first.sha256


def test_supersession_requires_reason_and_a_known_unchanged_file():
    first = _write(task="1", data=b"v1")
    with pytest.raises(store.CaseFileSupersessionWithoutReason):
        _write(task="2", supersedes=first)
    with pytest.raises(store.CaseFileNotFound):
        _write(task="2", supersedes="examinando/examinador/9/none.json",
               reason="x")
    first.path.write_bytes(b"changed")
    with pytest.raises(store.CaseFileTampered):
        _write(task="2", supersedes=first, reason="x")


def test_a_file_cannot_be_superseded_twice():
    first = _write(task="1", data=b"v1")
    _write(task="2", data=b"v2", supersedes=first, reason="correction")
    with pytest.raises(store.CaseFileAlreadySuperseded):
        _write(task="3", data=b"v3", supersedes=first, reason="another")


def test_superseder_claims_marker_first_so_a_second_one_fails_at_once(
        monkeypatch):
    """The race: superseder A claims the marker and stops before its own
    file lands. Superseder B must fail immediately with
    CaseFileAlreadySuperseded and write nothing; A's same write completes."""
    first = _write(task="1", data=b"v1")
    real_create_once = storage.create_once
    calls = []

    def crash_after_marker(target, data):
        calls.append(str(target))
        if str(target).endswith("output.json.json") and "\\2\\" in \
                str(target).replace("/", "\\"):
            raise RuntimeError("simulated crash after the claim")
        return real_create_once(target, data)

    monkeypatch.setattr(storage, "create_once", crash_after_marker)
    with pytest.raises(RuntimeError, match="simulated crash"):
        _write(task="2", data=b"v2-from-A", supersedes=first,
               reason="correction by A")
    marker = first.path.parent / ".meta" / "output.json.superseded_by"
    assert marker.exists()
    assert calls[0] == str(marker)       # claimed before any new-file byte

    monkeypatch.setattr(storage, "create_once", real_create_once)
    task_b = store.casefile_root(UNIT) / "examinando" / "examinador" / "3"
    with pytest.raises(store.CaseFileAlreadySuperseded):
        _write(task="3", data=b"v2-from-B", supersedes=first,
               reason="correction by B")
    assert not task_b.exists()           # B wrote nothing, not even meta

    with pytest.raises(store.CaseFileIncomplete):
        store.superseded_by(UNIT, first)  # dangling claim is reported
    with pytest.raises(store.CaseFileAlreadySuperseded):
        _write(task="2", data=b"v2-different", supersedes=first,
               reason="correction by A")  # not the same write: refused
    completed = _write(task="2", data=b"v2-from-A", supersedes=first,
                       reason="correction by A")
    assert [r.relative for r in store.superseded_by(UNIT, first)] == \
        [completed.relative]
    assert store.latest(UNIT, first).relative == completed.relative


def test_supersession_does_not_cross_cases():
    other_case = _write(unit=8, task="1", data=b"case 8")
    with pytest.raises(store.CaseFileNotFound):
        _write(unit=UNIT, task="1", supersedes=other_case.relative,
               reason="x")


def test_broken_link_is_reported_by_chain():
    first = _write(task="1", data=b"v1")
    second = _write(task="2", data=b"v2", supersedes=first, reason="fix")
    meta = first.path.parent / ".meta" / "output.json.json"
    body = json.loads(meta.read_text("utf-8"))
    first.path.write_bytes(b"replaced")
    body["sha256"] = hashlib.sha256(b"replaced").hexdigest()
    meta.write_text(json.dumps(body), "utf-8")
    with pytest.raises(store.CaseFileSupersessionBroken):
        store.chain(UNIT, second)


# --- writes outside the Case folder ------------------------------------------

@pytest.mark.parametrize("field,value", [
    ("task", "../escape"), ("task", "a/b"), ("name", ".."), ("name", "a\\b"),
    ("name", ".hidden"), ("name", "CON"), ("name", "nul.txt"), ("task", ""),
])
def test_path_segments_cannot_leave_the_case_folder(field, value,
                                                    operation_root):
    with pytest.raises(store.CaseFileInvalidSegment):
        _write(**{field: value})
    assert not (operation_root / "casos").exists() or \
        not any(p.is_file() for p in (operation_root / "casos").rglob("*"))


def test_unknown_stage_or_function_is_refused():
    with pytest.raises(store.CaseFileUnknownStage):
        _write(stage="SOMEWHERE")
    with pytest.raises(store.CaseFileUnknownFunction):
        _write(function="agent")


def test_pen_write_scope_not_covering_the_case_refuses(tmp_path,
                                                       operation_root):
    with write_scope(tmp_path / "elsewhere", label="test"):
        with pytest.raises(WriteOutsideRoots):
            _write()
    assert not store.casefile_root(UNIT).exists() or \
        not any(p.is_file() for p in store.casefile_root(UNIT).rglob("*"))
    with write_scope(store.casefile_root(UNIT), label="test") as scope:
        record = _write()
    assert str(record.path) in scope.written


def test_a_resolved_target_outside_the_case_folder_is_refused(tmp_path):
    # The last guard after segment checks: whatever path is computed (e.g. a
    # link inside the folder pointing out), it must resolve inside it.
    root = store.casefile_root(UNIT)
    with pytest.raises(store.CaseFileOutsideCase):
        store._inside(root, tmp_path / "escape" / "x")
    with pytest.raises(store.CaseFileOutsideCase):
        store._inside(root, root)


# --- vocabulary --------------------------------------------------------------

def test_functions_match_the_operation_roles():
    from src.casefile.operations import ROLE_NAMES
    assert set(store.FUNCTIONS) == set(ROLE_NAMES)
