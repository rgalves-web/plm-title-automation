"""Declared local operation roots, content identity and atomic artifact writes."""
from __future__ import annotations

import hashlib
import os
import json
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def operation_root():
    return Path(os.environ.get('PLM_OPERATION_ROOT',str(REPO_ROOT.parent/'PLM_OPERACAO'))).resolve()


def case_root(unit_id):
    if int(unit_id)<1:
        raise ValueError('invalid_case_id')
    return operation_root()/'casos'/str(int(unit_id))


def digest_file(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):
            h.update(chunk)
    return h.hexdigest()


def safe_target(unit_id, relative):
    root=case_root(unit_id).resolve()
    target=(root/relative).resolve()
    if target==root or not target.is_relative_to(root):
        raise ValueError('operation_write_outside_case')
    return target


def write_bytes(unit_id, relative, data):
    target=safe_target(unit_id,relative)
    sha=hashlib.sha256(data).hexdigest()
    if target.exists():
        if digest_file(target)!=sha:
            raise ValueError('immutable_artifact_conflict')
        return target,sha
    target.parent.mkdir(parents=True,exist_ok=True)
    temporary=target.with_name(target.name+'.'+str(os.getpid())+'.tmp')
    try:
        with temporary.open('xb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary,target)
    finally:
        if temporary.exists():
            temporary.unlink()
    if digest_file(target)!=sha:
        raise ValueError('artifact_roundtrip_failed')
    return target,sha


def create_once(target, data):
    """Create `target` with `data` atomically and never over an existing file.

    The bytes go to a temporary sibling first (flushed and fsynced), then are
    hard-linked into place: the link fails with FileExistsError when the target
    already exists, so two writers can never both win and a reader never sees a
    partial file. Filesystems without hard links fall back to an exclusive
    create. Returns the sha256 of what is on disk after a round-trip read."""
    target=Path(target)
    sha=hashlib.sha256(data).hexdigest()
    target.parent.mkdir(parents=True,exist_ok=True)
    temporary=target.with_name('.'+target.name+'.'+str(os.getpid())+'.'+os.urandom(6).hex()+'.tmp')
    try:
        with temporary.open('xb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary,target)
        except FileExistsError:
            raise
        except OSError:
            with target.open('xb') as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
    finally:
        if temporary.exists():
            temporary.unlink()
    if digest_file(target)!=sha:
        raise ValueError('artifact_roundtrip_failed')
    return sha


def checked_artifact(artifact):
    path=preserved_path(artifact['path'])
    if not path.is_file() or digest_file(path)!=artifact['sha256']:
        raise ValueError('artifact_missing_or_changed')
    return path


@lru_cache(maxsize=1)
def _aliases(path,mtime):
    return {key.casefold():value for key,value in json.loads(Path(path).read_text('utf-8')).items()}


def preserved_path(path):
    original=Path(path).resolve()
    if original.is_file(): return original
    mapping=operation_root()/'migracao'/'aliases.json'
    if not mapping.exists(): return original
    entry=_aliases(str(mapping),mapping.stat().st_mtime_ns).get(str(original).casefold())
    if not entry: return original
    target=Path(entry['path']).resolve()
    permitted=any(target.is_relative_to((operation_root()/folder).resolve()) for folder in ('casos','historico'))
    permitted=permitted or target.is_relative_to((REPO_ROOT.parent/'Land Cibola Surface Titles'/'Terrell County').resolve())
    if not permitted or not target.is_file() or digest_file(target)!=entry['sha256']:
        raise ValueError('preserved_source_reference_invalid')
    return target
