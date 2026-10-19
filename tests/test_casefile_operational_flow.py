"""Synthetic pipeline against PostgreSQL; no paid inference or legal conclusions."""
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from tests.test_casefile_operations import operation_case,approve,task,request,RESEARCH
from tests.helpers_casefile import ClientRoteirizado,Use,unit_de_teste
from src.casefile import worker,operations,runtime,training,training_runtime,learning
from src.casefile.repo import Repo
from src.casefile.storage import digest_file


def source(repo,unit,path):
    import fitz
    with fitz.open() as pdf:
        pdf.new_page().insert_text((30,60),'Synthetic fixture only. Field A = sample.')
        pdf.save(path)
    sha=digest_file(path)
    repo.registrar_source_file(sha,path.stat().st_size)
    return repo.operation_add_artifact(unit['id'],'source',path,sha,path.stat().st_size)


def run(repo,unit,steps):
    result=worker.executar_uma(repo,unit['id'],'synthetic-worker',teto=50,operation=True,client=ClientRoteirizado(steps))
    assert result['erros']==[]
    return result


@pytest.mark.parametrize('name',['read_page','ler_pagina'])
def test_arbitration_requires_own_page_receipt_and_exposes_role_reading_name(operation_case,tmp_path,name):
    repo,unit,scope=operation_case
    approve(repo,unit,scope)
    artifact=source(repo,unit,tmp_path/'arbitration.pdf')
    created=task(repo,unit,'arbitro','adjudicacao',mode='operador',
                 data={'claim':{'id':7},'verification':{'id':8}})
    active={**created,'_operation_run_id':12345}
    output={'claim_id':7,'verificacao_id':8,'desfecho':'mantido','material_conclusao_titulo':False,
            'justificativa':'Synthetic plumbing only.','documento':'sha256:'+artifact['sha256'],
            'pagina':'1','trecho':'Synthetic fixture only.'}
    assert runtime.check_arbitration(repo,active,output)==['arbitration_source_page_not_read_in_this_run']
    funcs=runtime.tools(repo,active)
    ctx=worker.montar_contexto(active,ferramentas_disponiveis=set(funcs))
    assert 'ler_pagina' in ctx['ferramentas'] and 'ler_pagina' not in ctx['indisponiveis']
    assert 'Ferramentas expostas' in ctx['tarefa'] and 'caminho de gravacao' in ctx['tarefa']
    funcs[name][1](output['documento'],1,'texto')
    assert runtime.check_arbitration(repo,active,output)==[]
    assert runtime.check_arbitration(repo,{**active,'_operation_run_id':54321},output)
    assert runtime.check_arbitration(repo,active,{**output,'claim_id':9})==['arbitration_requested_identity_mismatch']
    assert runtime.check_arbitration(repo,active,{**output,'verificacao_id':9})==['arbitration_requested_identity_mismatch']


def test_blind_range_requires_every_cited_page_in_current_run(operation_case,tmp_path):
    import fitz
    repo,unit,scope=operation_case
    approve(repo,unit,scope)
    path=tmp_path/'two-pages.pdf'
    with fitz.open() as pdf:
        for label in ('First synthetic page','Second synthetic page'):
            pdf.new_page().insert_text((30,60),label)
        pdf.save(path)
    sha=digest_file(path)
    repo.registrar_source_file(sha,path.stat().st_size)
    artifact=repo.operation_add_artifact(unit['id'],'source',path,sha,path.stat().st_size)
    primary=task(repo,unit,'examinador','claims',mode='obrigatoria')
    claim={'tipo':'fact','entidade':'Synthetic range','valor':{'tipo_resultado':'fato_documental','field':'sample'},'documento':'sha256:'+sha,
           'pagina':'1-2','trecho':'First synthetic page','confianca':'alta','materialidade':'baixa'}
    run(repo,unit,[[Use('entregar_saida',{'saida':{'claims':[claim]}})]])
    blind=next(t for t in repo.tarefas(unit['id']) if t['role']=='verificador')
    active={**blind,'_operation_run_id':12345}
    read=runtime.tools(repo,active)['ler_pagina_confirmada'][1]
    with pytest.raises(ValueError,match='page_mismatch'):read(sha,3,'texto')
    output={'valor':{},'trecho':'','evidencia_suficiente':False}
    read(sha,1,'texto')
    assert runtime.check_verification(repo,active,output)
    read(sha,2,'texto')
    assert runtime.check_verification(repo,active,output)==[]
    assert runtime.check_verification(repo,{**active,'_operation_run_id':54321},output)


def test_unlocated_claim_blocks_review_without_paid_request(operation_case,tmp_path):
    repo,unit,scope=operation_case
    approve(repo,unit,scope)
    artifact=source(repo,unit,tmp_path/'source.pdf')
    primary=task(repo,unit,'examinador','claims',mode='obrigatoria')
    claim={'tipo':'fact','entidade':'Synthetic unlocated source','valor':{'tipo_resultado':'fato_documental','field':'sample'},'documento':'sha256:'+artifact['sha256'],
           'pagina':'n/a','trecho':'Synthetic fixture only.','confianca':'baixa','materialidade':'alta'}
    run(repo,unit,[[Use('entregar_saida',{'saida':{'claims':[claim]}})]])
    blind=next(t for t in repo.tarefas(unit['id']) if t['role']=='verificador')
    assert blind['status']=='bloqueada' and not repo.runs_da_tarefa(blind['id'])
    assert repo.escalonamentos(unit['id'],abertos=True)


def test_case_worker_is_exclusive_while_other_cases_still_run(operation_case):
    from src.casefile import orquestracao
    repo,unit,scope=operation_case
    approve(repo,unit,scope)
    first=task(repo,unit);second=task(repo,unit)
    got=orquestracao.pegar(repo,unit['id'],'fixture-first',teto=50,max_active_per_unit=1)
    assert got and got[0]['id']==first['id']
    assert orquestracao.pegar(repo,unit['id'],'fixture-second',teto=50,max_active_per_unit=1) is None
    assert repo.tarefa(second['id'])['status']=='pronta'
    repo.fechar_run(got[1]['id'],'fixture-first',output_json=None,output_valid=False,validation_errors=[],stop_reason='fixture',para='bloqueada')
    assert orquestracao.pegar(repo,unit['id'],'fixture-second',teto=50,max_active_per_unit=1)[0]['id']==second['id']


def test_retrospective_json_and_literal_trace_sources_are_citable(operation_case,tmp_path):
    repo,unit,scope=operation_case
    approve(repo,unit,scope)
    path=tmp_path/'real-record.json';path.write_text('{"error": "synthetic_context_too_large"}\n',encoding='utf-8')
    artifact=repo.operation_add_artifact(unit['id'],'run_record',path,digest_file(path),path.stat().st_size)
    retro=task(repo,unit,'retrospectivo','fichas_candidatas',mode='operador')
    item={'sources':[{'artifact_id':artifact['id'],'quote':'synthetic_context_too_large'}]}
    assert learning.validate(repo,retro,{'fichas':[item]})==[]
    assert learning.validate(repo,retro,{'fichas':[{'sources':[{'artifact_id':artifact['id'],'quote':'invented'}]}]})
    receipt=runtime.tools(repo,retro)['ler_trilha_da_unit'][1](limite=5)
    saved=repo.operation_artifact(receipt['artifact_id'])
    assert Path(saved['path']).read_text('utf-8')==receipt['citation_source_text']
    assert training.text_parts(Path(saved['path']))


@pytest.mark.parametrize('materiality,expected',[('baixa','aceita'),('alta','aguardando_operador')])
def test_primary_blind_extraction_ai_comparison_and_formula_protection(operation_case,tmp_path,materiality,expected):
    from src.casefile import report_writer
    repo,unit,scope=operation_case
    approve(repo,unit,scope)
    artifact=source(repo,unit,tmp_path/'source.pdf')
    primary=task(repo,unit,'examinador','claims',mode='obrigatoria')
    claim={'tipo':'fact','entidade':'Synthetic field','valor':{'tipo_resultado':'fato_documental','field':'sample'},
           'documento':'sha256:'+artifact['sha256'],'pagina':'1','trecho':'Synthetic fixture only.',
           'confianca':'alta','materialidade':materiality}
    run(repo,unit,[[Use('entregar_saida',{'saida':{'claims':[claim]}})]])
    assert repo.tarefa(primary['id'])['status']=='aguardando_verificacao'
    blind=next(t for t in repo.tarefas(unit['id']) if t['role']=='verificador')
    assert 'value' not in blind['input_json'] and 'claim' not in blind['input_json']
    page={'documento':artifact['sha256'],'pagina':1,'modo':'texto'}
    assert runtime.tools(repo,blind)['ler_pagina_confirmada'][1](**page)['kind']=='text'
    run(repo,unit,[[Use('ler_pagina_confirmada',page)],[Use('entregar_saida',{'saida':{'valor':{'field':'independent sample'},'trecho':'Synthetic fixture only.','evidencia_suficiente':True}})]])
    cid=repo.claims_da_tarefa(primary['id'])[0]
    assert repo.verificacoes_do_claim(cid)[-1]['status']=='invalidada'
    assert repo.tarefa(primary['id'])['status']=='aguardando_verificacao'
    comparison={'claim_id':cid,'verdict':'concordancia','source_sha256':artifact['sha256'],'page':'1',
                'quote':'Synthetic fixture only.','reason':'Synthetic model-declared result, plumbing only.','material_divergence':False}
    run(repo,unit,[[Use('read_page',page)],[Use('entregar_saida',{'saida':comparison})]])
    assert repo.tarefa(primary['id'])['status']==expected
    if expected=='aguardando_operador':
        operations.command(repo,request(repo,unit,'decide_task',task_id=primary['id'],accept=True))
        assert repo.tarefa(primary['id'])['status']=='aceita'
    assert repo.verificacoes_do_claim(cid)[-1]['comparison']['ai_judgment'] is True
    import openpyxl
    workbook=openpyxl.Workbook();sheet=workbook.active;sheet.title='Surface';sheet['B1']='=1+1';sheet['A1']='Example';sheet['A1'].alignment=openpyxl.styles.Alignment(wrap_text=True)
    sheet['A1'].hyperlink='https://example.com/sample-document'
    sheet['A1'].comment=openpyxl.comments.Comment('Sample fact that must not survive','Synthetic fixture')
    template=tmp_path/'template.xlsx';workbook.save(template)
    entry=repo.operation_add_artifact(unit['id'],'template',template,digest_file(template),template.stat().st_size)
    repo.operation_update(unit['id'],profile={'template_artifact_id':entry['id'],'lead_example_artifact_id':entry['id'],
        'sample_data_clearance':'clear_declared_cells','sample_cells':[{'sheet':'Surface','cell_ref':'A1'}]})
    writer=task(repo,unit,'redator','projecao_celulas',mode='operador')
    listed=runtime.tools(repo,writer)['ler_claims_aceitos'][1]()
    assert [c['id'] for c in listed['claims']]==[cid] and listed['total']==1 and listed['next_offset'] is None
    assert report_writer.validate(repo,writer,{'celulas':[{'sheet':'Surface','cell_ref':'B1','value':'bad','claim_ids':[cid]}],'brancos':[]})
    run(repo,unit,[[Use('entregar_saida',{'saida':{'celulas':[{'sheet':'Surface','cell_ref':'A1','value':'Synthetic report value','claim_ids':[cid]}],'brancos':[]}})]])
    report=repo.operation_artifacts(unit['id'],'working_report')[-1]
    result=openpyxl.load_workbook(report['path'])
    assert result['Surface']['B1'].value=='=1+1' and result['Surface']['A1'].alignment.wrap_text
    assert result['Surface']['A1'].hyperlink is None and result['Surface']['A1'].comment is None
    assert digest_file(template)==entry['sha256']
    assert all(q['status']=='pending' for q in repo.operation_requirements(unit['id'],report['sha256']))


def test_checkpoint_claim_survives_lost_api_response_without_task_completion(operation_case,tmp_path):
    repo,unit,scope=operation_case
    approve(repo,unit,scope)
    artifact=source(repo,unit,tmp_path/'checkpoint-source.pdf')
    primary=task(repo,unit,'examinador','claims',mode='obrigatoria')
    claim={'tipo':'fact','entidade':'Synthetic field','valor':{'tipo_resultado':'fato_documental','field':'sample'},
           'documento':'sha256:'+artifact['sha256'],'pagina':'1','trecho':'Synthetic fixture only.',
           'confianca':'alta','materialidade':'baixa'}
    class Interrupted(ClientRoteirizado):
        def __init__(self):super().__init__([[Use('registrar_claims',{'claims':[claim]})]]);self.calls=0
        def create(self,**kwargs):
            self.calls+=1
            if self.calls==2:raise RuntimeError('Synthetic interrupted API after checkpoint')
            return super().create(**kwargs)
    result=worker.executar_uma(repo,unit['id'],'synthetic-worker',teto=50,operation=True,client=Interrupted())
    assert result['erros'] and repo.tarefa(primary['id'])['status']=='bloqueada'
    assert len(repo.claims_da_tarefa(primary['id']))==1
    assert len([t for t in repo.tarefas(unit['id']) if t['role']=='verificador'])==1
    assert repo.operation_artifacts(unit['id'],'claim_checkpoint')
    assert not repo.verificacoes_do_claim(repo.claims_da_tarefa(primary['id'])[0])


def test_checkpoint_replay_and_final_delivery_do_not_duplicate_claims(operation_case,tmp_path):
    repo,unit,scope=operation_case
    approve(repo,unit,scope)
    artifact=source(repo,unit,tmp_path/'checkpoint-source.pdf')
    primary=task(repo,unit,'examinador','claims',mode='obrigatoria')
    claim={'tipo':'fact','entidade':'Synthetic field','valor':{'tipo_resultado':'fato_documental','field':'sample'},
           'documento':'sha256:'+artifact['sha256'],'pagina':'1','trecho':'Synthetic fixture only.',
           'confianca':'alta','materialidade':'baixa'}
    run(repo,unit,[[Use('registrar_claims',{'claims':[claim]})],[Use('registrar_claims',{'claims':[claim]})],
                  [Use('entregar_saida',{'saida':{'claims':[claim]}})]])
    assert len(repo.claims_da_tarefa(primary['id']))==1
    assert len(repo.claims_da_unit(unit['id']))==1
    assert repo.tarefa(primary['id'])['status']=='aguardando_verificacao'
    assert len([t for t in repo.tarefas(unit['id']) if t['role']=='verificador'])==1


def test_four_cases_execute_concurrently_with_distinct_results(operation_case,tmp_path):
    from src.casefile.db import connect
    import os
    repo,first,scope=operation_case
    units=[first]+[unit_de_teste(repo,Path(first['folder_path']).parent/f'UNIT-{i}',f'UNIT-{i}') for i in range(3)]
    policy=repo.politica(first['id'],'project_profile')
    for unit in units:
        if unit['id']!=first['id']:
            repo.registrar_politica(unit['id'],'project_profile',policy)
            repo.operation_register(unit['id'],{**scope,'pid':'other' if unit==units[-1] else 'shared'})
        approve(repo,unit,scope)
        task(repo,unit)
    schema=repo.conn.execute('SELECT current_schema() AS name').fetchone()['name']
    barrier=Barrier(4)
    class Concurrent(ClientRoteirizado):
        def create(self,**kwargs):
            barrier.wait(timeout=20)
            return super().create(**kwargs)
    def execute(unit):
        with connect(os.environ['CASEFILE_TEST_DSN']) as conn:
            conn.execute("SELECT set_config('search_path',%s,false)",(schema,))
            own=Repo(conn)
            payload={**RESEARCH,'fonte':'local-'+str(unit['id'])}
            return worker.executar_uma(own,unit['id'],'test-'+str(unit['id']),teto=50,operation=True,
                client=Concurrent([[Use('entregar_saida',{'saida':payload})]]))
    with ThreadPoolExecutor(4) as executor:
        results=list(executor.map(execute,units))
    assert all(not r['erros'] for r in results)
    assert len({r['run_id'] for r in results})==4
    assert all(len(repo.buscas(u['id']))==1 for u in units)
    assert repo.conn.execute("SELECT count(*) AS n FROM operation_requests WHERE status='confirmed'").fetchone()['n']==4


def test_same_pid_shares_complete_query_other_pid_does_not(operation_case,tmp_path,monkeypatch):
    from src.casefile import source_adapters
    repo,first,scope=operation_case
    units=[first]+[unit_de_teste(repo,tmp_path/f'UNIT-{i}',f'QUERY-{i}') for i in range(2)]
    for index,unit in enumerate(units):
        repo.operation_register(unit['id'],scope)
        repo.operation_update(unit['id'],scope={**scope,'pid':'A' if index<2 else 'B','sources':['countyrecords'],'share_research':True})
    calls=[]
    def query(*args):
        calls.append(1)
        return {'pagination_complete':True,'saved_total':1,'reported_total':1,'results':['synthetic result']}
    monkeypatch.setattr(source_adapters,'portal_search',query)
    source_tasks=[task(repo,u) for u in units]
    receipts=[source_adapters.execute(repo,source_tasks[index],'countyrecords',{'terms':['synthetic'],'index':'grantor'}) for index,u in enumerate(units)]
    assert len(calls)==2
    assert receipts[1]['shared_origin_unit_id']==first['id']
    assert receipts[1]['territorial_application']=='pending_for_this_tract'
    assert 'shared_origin_job_id' not in receipts[-1]


def test_verified_candidate_human_batch_publication_pins_next_run(operation_case,tmp_path,monkeypatch):
    from tests.test_casefile_training import card
    repo,unit,scope=operation_case
    store=training.Store(tmp_path/'knowledge')
    base=card(tmp_path,project='Cibola');base['scope']['substance']=['surface'];base['scope']['work_type']=['surface_title']
    original=store.put(base)
    rid=store.publish([{'rule_id':original['rule_id'],'version':original['version']}],reviewer='human:fixture',reason='Synthetic initial release',reviewed_at='2026-10-11')
    context={k:v[0] for k,v in base['scope'].items()}
    repo.configure_training(unit['id'],{'release_id':rid,'scope':context,'store_root':str(store.root),'reviewer':'human:fixture','reason':'Fixture only'})
    monkeypatch.setattr(learning,'Store',lambda:store)
    proposed=store.put({**base,'rule_id':'candidate','interpretation':'Synthetic method correction'})
    lesson=repo.operation_add_lesson(unit['id'],None,proposed['version'],proposed)
    with pytest.raises(ValueError,match='unverified'):
        learning.review_batch(repo,unit['id'],[lesson['id']],True,'human:fixture','Fixture only')
    approve(repo,unit,scope)
    verification=task(repo,unit,'verificador','revisao_licao',mode='nenhuma',data={'lesson_id':lesson['id']})
    result=run(repo,unit,[[Use('entregar_saida',{'saida':{'source_quotes_confirmed':True,'methodology_only':True,'reason':'Synthetic independent reviewer'}})]])
    assert repo.run(result['run_id'])['model_family']=='B'
    assert repo.operation_lessons(unit['id'])[0]['status']=='verified'
    sid=repo.abrir_sessao(unit['id'],'tarefa:coordenador','fixture')
    training_runtime.prepare(repo,unit,sid,'tarefa:coordenador',store)
    new=learning.review_batch(repo,unit['id'],[lesson['id']],True,'human:fixture','Synthetic human approval')
    assert new!=rid
    assert next(c for c in repo.knowledge_audit(unit['id'])['contexts'] if c['session_id']==sid)['manifest']['release_id']==rid
    next_sid=repo.abrir_sessao(unit['id'],'tarefa:coordenador','fixture')
    training_runtime.prepare(repo,unit,next_sid,'tarefa:coordenador',store)
    assert repo.knowledge_audit(unit['id'])['contexts'][-1]['manifest']['release_id']==new
    learning.withdraw(repo,unit['id'],lesson['id'],'human:fixture','Synthetic withdrawal')
    assert repo.operation_lessons(unit['id'])[0]['status']=='withdrawn'


def test_lost_response_receipt_reconciles_once_and_allows_resume(operation_case,tmp_path,monkeypatch):
    from src.casefile import operator_actions
    repo,unit,scope=operation_case
    approve(repo,unit,scope);task(repo,unit)
    class Lost:
        messages=None
        def __init__(self):self.messages=self
        def create(self,**kwargs):raise RuntimeError('Synthetic lost response')
    worker.executar_uma(repo,unit['id'],'fixture',teto=50,operation=True,client=Lost())
    row=repo.conn.execute('SELECT * FROM operation_requests').fetchone()
    receipt=tmp_path/'receipt.txt';receipt.write_text('Synthetic provider confirms cost 0.02; not a real bill.')
    monkeypatch.setattr(operator_actions,'REPO_ROOT',tmp_path/'repo')
    body=request(repo,unit,'reconcile_usage',request_id=row['id'],cost_usd=.02,path=str(receipt))
    assert operations.command(repo,body)==operations.command(repo,body)
    assert repo.custo_acumulado(unit['id'])==.02
    from src.casefile.accounting import RunAccounting
    from tests.helpers_casefile import Msg
    closed=repo.run(row['run_id'])
    accounting=RunAccounting(repo,repo.tarefa(closed['task_id']),closed)
    accounting.request_id=row['id']
    accounting.response(Msg([]),{'input':10,'output':5},.03)
    assert repo.custo_acumulado(unit['id'])==.02
    operations.command(repo,request(repo,unit,'resume'))
    assert repo.operation_case(unit['id'])['execution_state']=='running'


def test_relocated_source_reference_keeps_exact_bytes(operation_case,tmp_path):
    from src.casefile.storage import operation_root,preserved_path,write_bytes
    repo,unit,scope=operation_case
    old=tmp_path/'old-control.txt';old.write_text('Original methodological source.\n',encoding='utf-8')
    sha=digest_file(old)
    target,_=write_bytes(unit['id'],'fontes/'+sha+'.txt',old.read_bytes())
    mapping=operation_root()/'migracao'/'aliases.json';mapping.parent.mkdir(parents=True)
    mapping.write_text(json.dumps({str(old.resolve()):{'path':str(target),'sha256':sha}}),encoding='utf-8')
    old.unlink()
    assert preserved_path(old)==target
    assert training.file_hash(old)==sha
    assert 'Original methodological source.' in '\n'.join(t for _,t in training.text_parts(old))
    target.write_text('Changed source')
    with pytest.raises(ValueError,match='preserved_source_reference_invalid'):
        preserved_path(old)


def test_command_api_and_event_reconnection(operation_case):
    from fastapi.testclient import TestClient
    from src.casefile.api import app,get_repo
    from src.casefile.operations_api import event_batch
    repo,unit,scope=operation_case
    app.dependency_overrides[get_repo]=lambda:repo
    try:
        with TestClient(app) as client:
            body=request(repo,unit,'pause')
            assert client.post('/api/operations/commands',json=body).status_code==403
            token=client.get('/api/operations/session').json()['command_token']
            headers={'x-plm-token':token,'origin':'http://malicious.invalid'}
            assert client.post('/api/operations/commands',json=body,headers=headers).status_code==403
            headers={'x-plm-token':token}
            result=client.post('/api/operations/commands',json=body,headers=headers)
            assert result.status_code==200
            assert client.post('/api/operations/commands',json=body,headers=headers).json()==result.json()
            assert client.post('/api/operations/commands',json={**body,'command_id':'stale-command-00001'},headers=headers).status_code==409
        snap,events=event_batch(repo,0)
        assert snap['last_event_id']==result.json()['event_id'] and events==[]
        cursor=snap['last_event_id']
        new=repo.operation_event('synthetic.changed','process:fixture',{},unit_id=unit['id'])
        assert event_batch(repo,cursor)[1][0]['id']==new['id']
        assert event_batch(repo,new['id'])[1]==[]
        assert event_batch(repo,new['id']+100)[0]['last_event_id']==new['id']
    finally:
        app.dependency_overrides.clear()


def test_coordinator_reallocates_inside_budget_and_isolates_cases(operation_case,tmp_path):
    repo,unit,scope=operation_case
    approve(repo,unit,scope)
    target=task(repo,unit,budget=1)
    coordinator=task(repo,unit,'coordenador','plano_tarefas',budget=2)
    update=runtime.tools(repo,coordinator)['atualizar_tarefa'][1]
    assert update(target['id'],'Synthetic allocation',budget_usd=2)['budget_usd']==2
    with pytest.raises(ValueError,match='exceeds_approved'):
        update(target['id'],'Synthetic over-allocation',budget_usd=100)
    other=unit_de_teste(repo,tmp_path/'OTHER','OTHER')
    other_task=task(repo,other)
    with pytest.raises(ValueError,match='case_task_required'):
        update(other_task['id'],'Synthetic cross-case edit',budget_usd=2)
    assert update(target['id'],'Synthetic cancellation',cancelar=True)['status']=='cancelada'


def test_incomplete_capture_and_wrong_claim_citation_are_named(operation_case,tmp_path):
    repo,unit,scope=operation_case
    artifact=source(repo,unit,tmp_path/'incomplete.pdf')
    repo.conn.execute("UPDATE operation_artifacts SET metadata=%s::jsonb WHERE id=%s",
        (json.dumps({'preview_page_count':2,'captured_pages':[1]}),artifact['id']))
    output={'estado':'capturado','sha256':artifact['sha256'],'caminho_staging':artifact['path'],'paginas':1}
    assert runtime.check_document(repo,{'unit_id':unit['id']},output)==['captured_document_incomplete_against_source_page_count']
    assert runtime.check_comparison(repo,{'input_json':{'claim':{'id':1}}},{'claim_id':2})==['comparison_claim_different_from_requested_claim']


def test_saved_search_results_are_read_in_windows_without_losing_population(operation_case):
    repo,unit,scope=operation_case
    created=task(repo,unit)
    job=repo.operation_source_request(unit['id'],'local','synthetic-window',{},task_id=created['id'])
    rows=[{'synthetic_row':i} for i in range(75)]
    repo.operation_source_result(job['id'],'complete',{'results':rows,'pagination_complete':True,'reported_total':75,'saved_total':75})
    read=runtime.tools(repo,created)['ler_resultados_busca'][1]
    first=read(job['id'],0,50);last=read(job['id'],50,50)
    assert len(first['results'])==50 and len(last['results'])==25
    assert first['saved_total']==last['saved_total']==75
    assert first['next_offset']==50 and last['next_offset'] is None
    assert len(repo.operation_sources(unit['id'])[0]['receipt']['results'])==75


def test_decision_rejects_different_result_even_with_current_case_revision(operation_case):
    repo,unit,scope=operation_case
    approve(repo,unit,scope)
    created=task(repo,unit,mode='operador')
    result=run(repo,unit,[[Use('entregar_saida',{'saida':RESEARCH})]])
    with pytest.raises(operations.OperationConflict,match='task_result_changed'):
        operations.command(repo,request(repo,unit,'decide_task',task_id=created['id'],accept=True,expected_run_id=result['run_id']+1))
    assert repo.tarefa(created['id'])['status']=='aguardando_operador'
    operations.command(repo,request(repo,unit,'decide_task',task_id=created['id'],accept=True,expected_run_id=result['run_id']))
    assert repo.tarefa(created['id'])['status']=='aceita'


def test_search_corpus_returns_results_and_is_cached(operation_case,tmp_path):
    repo,unit,scope=operation_case
    approve(repo,unit,scope)
    artifact=source(repo,unit,tmp_path/'searchable.pdf')
    examiner={**task(repo,unit,'examinador','claims',mode='obrigatoria'),'_operation_run_id':12345}
    search=runtime.tools(repo,examiner)['search_corpus'][1]
    found=search('Field A')
    assert found['populations']['no_texto']==1 and found['job_id']
    assert found['no_texto'][0]['documento'].startswith('sha256:'+artifact['sha256'])
    again=search('Field A')
    assert again['cached'] is True and again['job_id']==found['job_id']


def test_search_corpus_failure_is_a_named_error(operation_case,tmp_path,monkeypatch):
    from src.casefile.acervo import Acervo
    repo,unit,scope=operation_case
    approve(repo,unit,scope)
    source(repo,unit,tmp_path/'searchable.pdf')
    examiner={**task(repo,unit,'examinador','claims',mode='obrigatoria'),'_operation_run_id':12345}
    def broken(self,term):raise RuntimeError('synthetic failure')
    monkeypatch.setattr(Acervo,'search',broken)
    with pytest.raises(runtime.CorpusSearchError,match='corpus_search_failed: RuntimeError'):
        runtime.tools(repo,examiner)['search_corpus'][1]('Field A')


@pytest.mark.parametrize('mode',['texto','ocr','imagem'])
def test_reading_past_the_last_page_names_the_page_count(operation_case,tmp_path,mode):
    repo,unit,scope=operation_case
    approve(repo,unit,scope)
    artifact=source(repo,unit,tmp_path/'one-page.pdf')
    examiner={**task(repo,unit,'examinador','claims',mode='obrigatoria'),'_operation_run_id':12345}
    read=runtime.tools(repo,examiner)['ler_pagina'][1]
    for page in (2,'3',0):
        with pytest.raises(runtime.PageOutOfRange,match=r'page_out_of_range: .* tem 1 página\(s\)'):
            read('sha256:'+artifact['sha256'],page,mode)
    assert not repo.operation_events(unit_id=unit['id'],limit=50,kind='source.page_read')
    if mode=='texto':
        assert 'Field A' in read('sha256:'+artifact['sha256'],1,mode)['text']
