"""Resumable local inventory and migration intake. Never approves historical work."""
from __future__ import annotations
import json
import re
import os
from pathlib import Path

from src.casefile import agentes,orquestracao,project_profile
from src.casefile.storage import operation_root,write_bytes,digest_file
from src.casefile.training import digest

PILOT_NAMES={
 'BBT-SNN-2750-E - PID 16237','BBT-SNN-2750-E-1 - PID 16237',
 'BBT-SNN-2750-E-2 - PID 16237','BBT-SNN-1107 - PID 16142'}
SKIP_PARTS={'.git','__pycache__','_page_cache','node_modules','.venv','venv','.pytest_cache'}
SOURCE_EXTENSIONS={'.pdf','.png','.jpg','.jpeg','.tif','.tiff','.bmp'}


def inventory_files(root):
    for directory,dirs,files in os.walk(root,followlinks=False):
        dirs[:]=sorted(d for d in dirs if d not in SKIP_PARTS and not Path(directory,d).is_symlink())
        for name in sorted(files):
            if not name.startswith('~$'):
                yield Path(directory,name)


def inventory(repo,workspace,units=None):
    workspace=Path(workspace).resolve()
    candidates=units or [u for u in repo.listar_units() if u['canonical_name'] in PILOT_NAMES]
    seen={}
    aliases={}
    results=[]
    orquestracao.registrar_versoes(repo)
    for unit in candidates:
        uid=unit['id']
        previous=repo.operation_case(uid)
        if previous and previous['execution_state']=='running':
            raise ValueError('pause_case_before_inventory')
        folder=Path(unit['folder_path']).resolve()
        if not folder.is_relative_to(workspace):
            raise ValueError('migration_source_outside_workspace')
        match=re.search(r'PID[ _]+(\d+)',unit['canonical_name'])
        pid=match[1] if match else str(uid)
        profile=project_profile.selected(repo,unit)
        project=Path(profile['project_root']).resolve() if profile else folder.parent
        scope={'work_type':'surface_title','pid':pid,'county':'Terrell','start_date':'1966-01-01',
               'through_date':'2026-10-11','sources':['local','drive','countyrecords','texasfile','cad','rrc'],
               'share_research':True,'investigate_prior_rights':True,'status':'pending_operator_approval'}
        repo.operation_register(uid,scope,{'project_root':str(project),'intake':'historical_observations'})
        for source,reason in [('drive','Conectar o Drive e selecionar a pasta do caso'),('countyrecords','Validar a sessão e a rotina de busca/captura no CountyRecords'),('texasfile','Validar a sessão e a rotina de busca no TexasFile'),('cad','Validar a rotina de consulta territorial no CAD'),('rrc','Validar a rotina de consulta no RRC')]:
            job=repo.operation_source_request(uid,source,'setup:'+source,{'setup':True},impact='Pesquisa desta fonte aguarda acesso operacional verificado.')
            if job['status']=='requested':
                repo.operation_source_result(job['id'],'blocked',{'reason':reason,'owner':'Renato / configuração local','setup':True})
        roots=[folder]
        for control in sorted(project.glob('00_Controle_Local_*')):
            root=control/('PID_'+pid)
            if root.is_dir():
                roots.append(root)
        files=[]
        for root in roots:
            for source in inventory_files(root):
                if not source.is_file() or any(p in SKIP_PARTS for p in source.parts) or source.name.startswith('~$'):
                    continue
                original=source.resolve()
                if not original.is_relative_to(workspace):
                    raise ValueError('migration_source_symlink_outside_workspace')
                sha=digest_file(original)
                size=original.stat().st_size
                current=original
                control=root!=folder
                metadata={'display_name':original.name,'original_path':str(original),'sha256':sha,
                          'original_mtime':original.stat().st_mtime,'historical_status':'unreviewed_observation',
                          'allocation':'pending','imported_from_control':control,'title_approved':False}
                extension=original.suffix.lower()
                kind='source' if extension in SOURCE_EXTENSIONS else 'control_record'
                if not control and extension=='.xlsx' and original.parent.name.lower()=='1. landman submitted':
                    kind='working_report'
                    metadata['status']='WORKING DRAFT'
                    metadata['submission_read_only']=True
                key=(pid,sha)
                existing=seen.get(key)
                if existing:
                    # Content is shared; tract allocation and conclusions are not.
                    current=Path(existing['path'])
                    repo.operation_link_artifact(existing['id'],uid,{'status':'pending','origin':str(original)},'process:inventory')
                    artifact=existing
                else:
                    if control or kind=='working_report':
                        current,_=write_bytes(uid,'fontes/'+sha+extension,original.read_bytes())
                    artifact=repo.operation_add_artifact(uid,kind,current,sha,size,metadata)
                    seen[key]=artifact
                if kind=='source':
                    repo.registrar_source_file(sha,size)
                if kind=='working_report':
                    repo.operation_report_requirements(uid,sha)
                files.append({'original':str(original),'path':str(current),'sha256':sha,'size_bytes':size,
                              'artifact_id':artifact['id'],'kind':kind,'control':control})
                if control:
                    aliases[str(original)]={'path':str(current),'sha256':sha}
        body={'unit_id':uid,'canonical_name':unit['canonical_name'],'files':files,
              'states_preserved':True,'historical_acceptance_imported':False,'model_calls':0,'cost_usd':0}
        raw=json.dumps(body,ensure_ascii=False,indent=2).encode()
        identity=digest(body)
        path,sha=write_bytes(uid,'migracao/inventario_'+identity[:16]+'.json',raw)
        artifact=repo.operation_add_artifact(uid,'migration_manifest',path,sha,len(raw),{'schema':1,'recoverable':True})
        ref='inventory-'+identity[:20]
        if not repo.tarefa_por_ref(uid,ref):
            role=next(f for f in agentes.carregar() if f.nome=='arquivista' and f.tipo=='Role')
            task=repo.criar_tarefas(uid,[{'ref':ref,'role':'arquivista','pack':'title-texas-surface',
                'title':'Inventariar fontes e registros existentes','input_json':{'manifest_artifact_id':artifact['id'],'local_io_only':True},
                'output_schema':'inventario_registrado','acceptance':'Identidade e caminhos preservados; nenhuma aprovação de title.',
                'depends_on_refs':[],'budget_usd':0,'priority':-1000000,'verificacao':'nenhuma'}],'process:inventory')[0]
            repo.promover_prontas(uid,'process:inventory')
            pack=next(f for f in agentes.carregar() if f.tipo=='Domain Pack' and f.nome=='title-texas-surface')
            got=repo.pegar_tarefa(uid,'process:inventory',{'arquivista':agentes.versao(role.caminho)},
                                 {'title-texas-surface':agentes.versao(pack.caminho)},900,())
            if not got or got[0]['id']!=task['id']:
                raise ValueError('inventory_task_dispatch_conflict')
            repo.fechar_run(got[1]['id'],'process:inventory',output_json={'files':len(files),'manifest_sha256':sha,'title_approved':False},
                            output_valid=True,validation_errors=[],stop_reason='local_inventory_complete',para='aceita',
                            model='Sistema local · inventário',model_family='local_io',cost_usd=0)
            repo.operation_event('case.imported','process:inventory',{'files':len(files),'manifest_artifact_id':artifact['id'],
                                      'model_calls':0,'title_approved':False},unit_id=uid,task_id=task['id'])
        results.append({'unit_id':uid,'files':len(files),'manifest_artifact_id':artifact['id']})
    target=operation_root()/'migracao'/'aliases.json'
    target.parent.mkdir(parents=True,exist_ok=True)
    old=json.loads(target.read_text('utf-8')) if target.exists() else {}
    target.write_text(json.dumps({**old,**aliases},ensure_ascii=False,indent=2),encoding='utf-8')
    return results


def prepare():
    from src.casefile.db import connect,migrar
    from src.casefile.repo import Repo
    recovery=operation_root()/'recuperacao'/'antes_esteira_2026-10-11'/'casefile.dump'
    if not recovery.is_file():
        raise ValueError('database_recovery_snapshot_required_before_migration')
    with connect() as conn:
        migrations=migrar(conn)
        repo=Repo(conn)
        results=inventory(repo,Path(__file__).resolve().parents[3])
    return {'migrations':migrations,'cases':results,'model_calls':0,'cost_usd':0,'title_approved':False}
