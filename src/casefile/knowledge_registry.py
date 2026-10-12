"""One version registry for roles, OKF and Training Suite; importing activates nothing."""
from pathlib import Path
import hashlib
import json
import os
from uuid import uuid4

from src.casefile.storage import REPO_ROOT,operation_root,digest_file
from src.casefile.training import ROOT,digest
from src.casefile.repo import _json


def preserve(path):
    return preserve_bytes(path.read_bytes(),path.suffix.lower())


def preserve_bytes(raw,suffix):
    sha=hashlib.sha256(raw).hexdigest()
    target=operation_root()/'conhecimento'/'fontes'/(sha+suffix)
    target.parent.mkdir(parents=True,exist_ok=True)
    if not target.exists():
        temporary=target.with_name(target.name+'.'+uuid4().hex+'.tmp')
        try:
            with temporary.open('xb') as stream:
                stream.write(raw);stream.flush();os.fsync(stream.fileno())
            os.replace(temporary,target)
        finally:
            if temporary.exists():temporary.unlink()
    if digest_file(target)!=sha:raise ValueError('knowledge_preservation_changed')
    return raw,sha,target


def import_sources(repo,root=REPO_ROOT,training_root=ROOT):
    import yaml
    root=Path(root)
    sources=[(p,'legacy_okf') for p in (root/'knowledge_okf').glob('*.md')]
    sources +=[(p,'agent_card') for p in (root/'agentes').rglob('*.md')]
    sources +=[(p,'training_card') for p in (Path(training_root)/'cards').rglob('*.json')]
    sources +=[(p,'training_release') for p in (Path(training_root)/'releases').glob('*.json')]
    total=0
    for path,kind in sorted(sources,key=lambda v:str(v[0])):
        raw,sha,target=preserve(path)
        text=raw.decode('utf-8-sig')
        if path.suffix=='.json':data=json.loads(text)
        else:
            front={}
            if text.replace('\r\n','\n').startswith('---\n'):
                parts=text.split('---',2)
                if len(parts)==3:front=yaml.safe_load(parts[1]) or {}
            data={'frontmatter':front,'raw_markdown':text}
        data=json.loads(json.dumps(data,default=str,ensure_ascii=False))
        front=data.get('frontmatter',data)
        scope=front.get('scope') or front.get('escopo') or {'declared_unit':front.get('unit',''),'applicability':'unconfirmed'}
        key=kind+':'+str(path.relative_to(root) if path.is_relative_to(root) else path.name).replace('\\','/')
        version=digest({'key':key,'sha256':sha})
        binding={'import_activates_nothing':True,'declared_status':front.get('status','historical'),
                 'activation':'existing_execution_role_binding' if kind=='agent_card' and front.get('type') in ('Role','Domain Pack') else 'requires_existing_or_new_publication_decision',
                 'original_references_preserved':True}
        repo.conn.execute('INSERT INTO knowledge_registry_versions(version,registry_key,kind,source_sha256,original_path,preserved_path,scope,content,binding) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(version) DO NOTHING',
            (version,key,kind,sha,str(path),str(target),_json(scope),_json(data),_json(binding)))
        total+=1
    # Executions already pinned earlier role bytes in PostgreSQL. Preserve
    # those too; only importing today's files would lose earlier instructions.
    for row in repo.conn.execute('SELECT * FROM role_versions ORDER BY first_seen,sha256').fetchall():
        raw,sha,target=preserve_bytes(row['content'].encode('utf-8'),'.md')
        if sha!=row['sha256']:raise ValueError('historical_role_bytes_differ_from_execution_version')
        text=raw.decode('utf-8-sig');front={}
        if text.replace('\r\n','\n').startswith('---\n'):
            parts=text.split('---',2)
            if len(parts)==3:front=yaml.safe_load(parts[1]) or {}
        data=json.loads(json.dumps({'frontmatter':front,'raw_markdown':text},default=str,ensure_ascii=False))
        front=data['frontmatter'];scope=front.get('scope') or front.get('escopo') or {'applicability':'unconfirmed'}
        key='agent_card:'+row['path'].replace('\\','/')
        version=digest({'key':key,'sha256':sha})
        binding={'import_activates_nothing':True,'historical_execution_role_version':sha,'first_seen':str(row['first_seen']),'activation':'requires_existing_or_new_publication_decision'}
        repo.conn.execute('INSERT INTO knowledge_registry_versions(version,registry_key,kind,source_sha256,original_path,preserved_path,scope,content,binding) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(version) DO NOTHING',
            (version,key,'agent_card',sha,row['path'],str(target),_json(scope),_json(data),_json(binding)))
    return {'files_preserved':total,'registered_versions':repo.conn.execute('SELECT count(*) AS n FROM knowledge_registry_versions').fetchone()['n'],'new_activations':0}


def overview(repo):
    if not repo.conn.execute("SELECT to_regclass('knowledge_registry_versions') IS NOT NULL AS ok").fetchone()['ok']:return {'installed':False,'versions':[]}
    total=repo.conn.execute('SELECT count(*) AS n FROM knowledge_registry_versions').fetchone()['n']
    kinds=repo.conn.execute('SELECT kind,count(*) AS n FROM knowledge_registry_versions GROUP BY kind ORDER BY kind').fetchall()
    return {'installed':True,'total_versions':total,'by_kind':kinds,
            'versions':repo.conn.execute('SELECT version,registry_key,kind,source_sha256,scope,binding,registered_at FROM knowledge_registry_versions ORDER BY registry_key,registered_at LIMIT 50').fetchall(),
            'import_activates_nothing':True}
