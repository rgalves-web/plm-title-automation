import json
from pathlib import Path
from src.casefile import knowledge_registry as registry
from tests.test_casefile_operations import operation_case


def test_import_preserves_bytes_scope_dates_and_all_versions_without_activation(operation_case,tmp_path,monkeypatch):
    repo,unit,_=operation_case
    root=tmp_path/'repo';(root/'knowledge_okf').mkdir(parents=True);(root/'agentes').mkdir()
    training_root=root/'training';(training_root/'cards').mkdir(parents=True);(training_root/'releases').mkdir()
    preserved=tmp_path/'operation';monkeypatch.setattr(registry,'operation_root',lambda:preserved)
    path=root/'agentes'/'role.md'
    raw=b'---\r\ntype: Role\r\nat: 2026-10-12\r\nscope: {project: [Cibola]}\r\n---\r\nFirst source version.\r\n'
    path.write_bytes(raw)
    (root/'knowledge_okf'/'old.md').write_text('Historical scope unknown.',encoding='utf-8')
    first=registry.import_sources(repo,root,training_root)
    assert first['new_activations']==0
    assert registry.import_sources(repo,root,training_root)['registered_versions']==first['registered_versions']
    rows=repo.conn.execute('SELECT * FROM knowledge_registry_versions WHERE original_path=%s',(str(path),)).fetchall()
    assert len(rows)==1 and Path(rows[0]['preserved_path']).read_bytes()==raw
    assert rows[0]['scope']=={'project':['Cibola']}
    assert rows[0]['content']['frontmatter']['at']=='2026-10-12'
    path.write_bytes(raw.replace(b'First source',b'Second source'))
    registry.import_sources(repo,root,training_root)
    rows=repo.conn.execute('SELECT * FROM knowledge_registry_versions WHERE original_path=%s',(str(path),)).fetchall()
    assert len(rows)==2 and any(Path(r['preserved_path']).read_bytes()==raw for r in rows)
    import hashlib
    older=raw.replace(b'First source',b'Older database source')
    repo.registrar_versao_ficha(hashlib.sha256(older).hexdigest(),'agentes/role.md','Role','fixture',older.decode())
    registry.import_sources(repo,root,training_root)
    history=repo.conn.execute('SELECT * FROM knowledge_registry_versions WHERE source_sha256=%s',(hashlib.sha256(older).hexdigest(),)).fetchone()
    assert history and Path(history['preserved_path']).read_bytes()==older
    assert not repo.operation_lessons(unit['id'])
