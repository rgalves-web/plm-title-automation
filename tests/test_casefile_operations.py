"""Operational contracts and failures on isolated PostgreSQL schemas. No model calls."""
import json
from pathlib import Path
from uuid import uuid4

import pytest

from src.casefile import operations,worker,orquestracao
from src.casefile.db import migrar
from src.casefile.repo import Repo
from src.casefile.storage import digest_file
from tests.helpers_casefile import conectar_pg_ou_skip,unit_de_teste,ClientRoteirizado,Use,Texto


@pytest.fixture
def operation_case(tmp_path,monkeypatch):
    connection,schema=conectar_pg_ou_skip()
    migrar(connection)
    repo=Repo(connection)
    unit=unit_de_teste(repo,tmp_path/'PROJECT'/'UNIT')
    root=Path(unit['folder_path']).parent
    root.mkdir(parents=True,exist_ok=True)
    source=root/'scope.md'
    source.write_text('Synthetic scope only. No title conclusion.',encoding='utf-8')
    profile={'schema':1,'work_type':'surface_title','name':'synthetic','project_root':str(root),
             'planning_system':'synthetic','planning_task':'synthetic',
             'sources':[{'path':str(source),'sha256':digest_file(source)}]}
    repo.registrar_politica(unit['id'],'project_profile',json.dumps(profile))
    scope={'work_type':'surface_title','pid':'test','county':'Terrell','start_date':'1966-01-01',
           'through_date':'2026-10-11','sources':['local']}
    repo.operation_register(unit['id'],scope)
    monkeypatch.setenv('PLM_OPERATION_ROOT',str(tmp_path/'OPERATIONS'))
    monkeypatch.setenv('PLM_PAGE_CACHE',str(tmp_path/'CACHE'))
    try:
        yield repo,unit,scope
    finally:
        connection.execute(f'DROP SCHEMA "{schema}" CASCADE')
        connection.close()


def request(repo,unit,action,**extra):
    return {'command_id':uuid4().hex,'unit_id':unit['id'],'expected_revision':repo.operation_case(unit['id'])['revision'],
            'action':action,'note':'Explicit synthetic operator decision.',**extra}


def approve(repo,unit,scope):
    operations.command(repo,request(repo,unit,'start',budget_usd=50,scope=scope,turn_cap=200))
    coord=repo.tarefas(unit['id'])[0]
    repo.transicionar_tarefa(coord['id'],('pronta',),'cancelada','human:test','Only run the tested role.')


def task(repo,unit,role='pesquisador',schema='resultado_pesquisa',budget=1,mode='nenhuma',data=None):
    orquestracao.registrar_versoes(repo)
    created=repo.criar_tarefas(unit['id'],[{'ref':uuid4().hex,'role':role,'pack':'title-texas-surface','title':'Synthetic contract',
        'input_json':data or {},'output_schema':schema,'acceptance':'Persistence only, no title approval.',
        'depends_on_refs':[],'budget_usd':budget,'priority':0,'verificacao':mode}],'process:test')[0]
    repo.promover_prontas(unit['id'],'process:test')
    return created


RESEARCH={'fonte':'local','encontrados':[],
          'busca_negativa':[{'target':'synthetic','terms':['synthetic'],'scope':'synthetic names only',
              'populacao':'synthetic files','intervalo':{'de':'1966-01-01','ate':'2026-10-11'},
              'tipos_documentais':['synthetic'],'cobertura_fonte':'names only','names_scanned':0,'hits':[]}],
          'pedidos_de_captura':[]}


def test_budget_not_approved_does_not_dispatch(operation_case):
    repo,unit,scope=operation_case
    created=task(repo,unit)
    client=ClientRoteirizado([[Use('entregar_saida',{'saida':RESEARCH})]])
    with pytest.raises(ValueError,match='execution_not_running'):
        worker.executar_uma(repo,unit['id'],'test',teto=50,operation=True,client=client)
    assert repo.tarefa(created['id'])['status']=='pronta'
    assert repo.runs_da_tarefa(created['id'])==[]
    assert repo.custo_acumulado(unit['id'])==0


def test_operator_command_replay_and_stale_revision(operation_case):
    repo,unit,scope=operation_case
    body=request(repo,unit,'start',budget_usd=50,scope=scope,turn_cap=200)
    result=operations.command(repo,body)
    assert operations.command(repo,body)==result
    assert len(repo.tarefas(unit['id']))==1
    with pytest.raises(operations.OperationConflict,match='case_changed'):
        operations.command(repo,{**body,'command_id':uuid4().hex,'action':'pause'})
    assert repo.estado_da_unit(unit['id'])=='INDICADA'


@pytest.mark.parametrize('budget',[0,-1,51,float('nan'),float('inf')])
def test_invalid_budget_cannot_authorize(operation_case,budget):
    repo,unit,scope=operation_case
    with pytest.raises(ValueError,match='explicit_budget'):
        operations.command(repo,request(repo,unit,'start',budget_usd=budget,scope=scope))
    assert not repo.operation_case(unit['id'])['approval']


def test_research_output_and_usage_persist_once(operation_case):
    repo,unit,scope=operation_case
    approve(repo,unit,scope)
    created=task(repo,unit)
    client=ClientRoteirizado([[Use('entregar_saida',{'saida':RESEARCH})]])
    result=worker.executar_uma(repo,unit['id'],'test',teto=50,operation=True,client=client)
    assert not result['erros']
    assert repo.tarefa(created['id'])['status']=='aceita'
    assert len(repo.buscas(unit['id']))==1
    assert repo.buscas(unit['id'])[0]['result']=='pendente_julgamento'
    receipts=repo.conn.execute('SELECT * FROM operation_requests').fetchall()
    assert len(receipts)==1 and receipts[0]['status']=='confirmed'
    assert repo.custo_acumulado(unit['id'])==result['custo_usd']
    assert repo.estado_da_unit(unit['id'])=='INDICADA'


def test_persistence_failure_rolls_back_result_but_keeps_usage(operation_case,monkeypatch):
    from src.casefile import runtime
    repo,unit,scope=operation_case
    approve(repo,unit,scope)
    created=task(repo,unit)
    def failed(repo,task,output,sid,**kwargs):
        repo.inserir_pesquisa(unit['id'],'must roll back','w','where','method',sid,[])
        raise ValueError('injected_storage_failure')
    monkeypatch.setattr(runtime,'handlers',lambda:{'resultado_pesquisa':(lambda *a,**k:[],failed)})
    result=worker.executar_uma(repo,unit['id'],'test',teto=50,operation=True,
                              client=ClientRoteirizado([[Use('entregar_saida',{'saida':RESEARCH})]]))
    assert result['erros']
    assert repo.pesquisas(unit['id'])==[]
    assert repo.tarefa(created['id'])['status']=='aguardando_operador'
    assert repo.custo_acumulado(unit['id'])==result['custo_usd']


def test_lost_response_blocks_new_spending(operation_case):
    repo,unit,scope=operation_case
    approve(repo,unit,scope)
    created=task(repo,unit)
    class Lost:
        messages=None
        def __init__(self):self.messages=self
        def create(self,**kwargs):raise RuntimeError('synthetic lost response')
    result=worker.executar_uma(repo,unit['id'],'test',teto=50,operation=True,client=Lost())
    assert repo.operation_case(unit['id'])['execution_state']=='waiting'
    assert repo.runs_da_tarefa(created['id'])[-1]['usage_state']=='unknown'
    assert repo.sessoes_da_unit(unit['id'])[-1]['cost_usd'] is None
    assert result['erros']


def test_credit_rejection_blocks_first_attempt_without_output_or_charge(operation_case):
    repo,unit,scope=operation_case
    approve(repo,unit,scope)
    created=task(repo,unit)
    class Rejection(RuntimeError):
        status_code=400
        request_id='req_credit_test'
        body={'error':{'message':'Your credit balance is too low to access the Anthropic API.'}}
    class NoCredit:
        def __init__(self):self.messages=self;self.calls=0
        def create(self,**kwargs):
            self.calls+=1
            raise Rejection('raw error must not appear in diagnostics')
    client=NoCredit()
    result=worker.executar_uma(repo,unit['id'],'test',teto=50,operation=True,client=client)
    assert client.calls==1 and result['parada']=='provider_credit_balance_insufficient'
    assert repo.tarefa(created['id'])['status']=='bloqueada'
    assert len(repo.runs_da_tarefa(created['id']))==1
    assert repo.operation_case(unit['id'])['execution_state']=='waiting'
    assert float(repo.operation_case(unit['id'])['approved_budget_usd'])==50
    assert repo.custo_acumulado(unit['id'])==0
    receipt=repo.conn.execute('SELECT * FROM operation_requests').fetchone()
    assert receipt['status']=='nonbillable' and receipt['provider_request_id']=='req_credit_test'
    assert repo.sessoes_da_unit(unit['id'])[-1]['stop_reason']=='provider_credit_balance_insufficient'
    assert any(e['motivo']=='provider_access' for e in repo.escalonamentos(unit['id'],abertos=True))
    with pytest.raises(ValueError,match='execution_not_running'):
        worker.executar_uma(repo,unit['id'],'another',teto=50,operation=True,client=client)
    assert client.calls==1


def test_repeated_invalid_deliveries_block_without_new_task_attempt(operation_case):
    repo,unit,scope=operation_case
    approve(repo,unit,scope)
    created=task(repo,unit)
    bad={'unexpected':'synthetic invalid output'}
    client=ClientRoteirizado([[Use('entregar_saida',{'saida':bad})] for _ in range(4)])
    result=worker.executar_uma(repo,unit['id'],'test',teto=50,operation=True,client=client)
    assert result['parada']=='no_progress_after_two_retries'
    assert repo.tarefa(created['id'])['status']=='bloqueada'
    assert len(repo.runs_da_tarefa(created['id']))==1
    assert len(repo.conn.execute('SELECT * FROM operation_requests').fetchall())==3
    assert repo.operation_case(unit['id'])['execution_state']=='waiting'


def test_throttled_requests_retry_only_twice_in_application(operation_case,monkeypatch):
    import time
    repo,unit,scope=operation_case
    approve(repo,unit,scope)
    created=task(repo,unit)
    class Throttle(RuntimeError):
        status_code=429
        request_id='req_throttle_test'
        body={'error':{'message':'rate limited'}}
    class Limited:
        def __init__(self):self.messages=self;self.calls=0
        def create(self,**kwargs):self.calls+=1;raise Throttle('rate limited')
    client=Limited()
    delays=[]
    monkeypatch.setattr(time,'sleep',delays.append)
    result=worker.executar_uma(repo,unit['id'],'test',teto=50,operation=True,client=client)
    assert client.calls==3 and delays==[1,2]
    assert result['parada']=='provider_rate_limited'
    assert len(repo.runs_da_tarefa(created['id']))==1
    assert repo.tarefa(created['id'])['status']=='bloqueada'
    assert repo.conn.execute('SELECT count(*) AS n FROM operation_requests WHERE status=\'nonbillable\'').fetchone()['n']==3
    assert repo.custo_acumulado(unit['id'])==0


def test_template_inspection_handles_missing_border_sides(tmp_path):
    import openpyxl
    from openpyxl.styles import Border
    from src.casefile.report_writer import inspected
    workbook=openpyxl.Workbook()
    workbook.active['A1']='Synthetic template label'
    workbook.active['A1'].border=Border(left=None,right=None,top=None,bottom=None)
    path=tmp_path/'template.xlsx'
    workbook.save(path)
    result=inspected(path)
    assert result['sheets'][0]['cells'][0]['border']==dict.fromkeys(('left','right','top','bottom'))


def test_large_historical_decision_is_bounded_and_fully_retrievable(operation_case):
    from src.casefile import runtime
    repo,unit,scope=operation_case
    value='Unique synthetic record. '+('large history ' * 30000)
    repo.registrar_politica(unit['id'],'historical_test',value)
    created=task(repo,unit,'coordenador','plano_tarefas')
    read=runtime.tools(repo,created)['ler_case_file'][1]
    result=read(secao='decisoes',limite=100)
    assert len(json.dumps(result))<25000
    row=next(r for r in result['rows'] if r.get('question')=='[historical_test]')
    assert row['total_characters']>400000 and row['read_full_with']['registro_id']==row['id']
    parts=[];offset=0
    while True:
        part=read(secao='decisoes',registro_id=row['id'],text_offset=offset)
        assert len(part['text'])<=6000
        parts.append(part['text'])
        if part['next_text_offset'] is None:break
        offset=part['next_text_offset']
    assert json.loads(''.join(parts))['answer']==value
    with pytest.raises(ValueError,match='record_not_found'):
        read(secao='decisoes',registro_id=999999)


def test_each_request_has_its_own_usage_and_live_known_cost(operation_case):
    repo,unit,scope=operation_case
    approve(repo,unit,scope)
    created=task(repo,unit)
    client=ClientRoteirizado([[Use('ler_case_file',{'secao':'tarefas'})],[Use('entregar_saida',{'saida':RESEARCH})]])
    result=worker.executar_uma(repo,unit['id'],'test',teto=50,operation=True,client=client)
    receipts=repo.conn.execute('SELECT * FROM operation_requests ORDER BY ordinal').fetchall()
    assert not result['erros'] and len(receipts)==2
    assert receipts[0]['usage']['entrada_total']==receipts[1]['usage']['entrada_total']
    assert repo.sessoes_da_unit(unit['id'])[-1]['usage']['entrada_total']==2*receipts[0]['usage']['entrada_total']
    assert float(repo.runs_da_tarefa(created['id'])[-1]['cost_usd'])==sum(float(q['cost_usd']) for q in receipts)


def test_decision_packet_preserves_source_identity_and_pending_requirements(operation_case,tmp_path):
    import zipfile
    from src.casefile.operation_packet import build
    repo,unit,scope=operation_case
    source=tmp_path/'original_source.txt';source.write_text('Synthetic source, not title evidence.',encoding='utf-8')
    sha=digest_file(source)
    artifact=repo.operation_add_artifact(unit['id'],'source',source,sha,source.stat().st_size)
    repo.abrir_escalonamento(unit['id'],None,'synthetic_dependency','Provide complete synthetic document.',['supply document'])
    result=build(repo,unit['id'])
    with zipfile.ZipFile(result['path']) as packet:
        manifest=json.loads(packet.read('casefile.json'))
        assert manifest['status']=='WORKING DRAFT' and not manifest['title_approval']
        assert manifest['artifacts'][0]['sha256']==sha
        assert manifest['metrics']['operator_time_minutes'] is None
        assert manifest['decisions'][0]['pergunta']=='Provide complete synthetic document.'
    assert digest_file(source)==sha
    repo.operation_update(unit['id'],execution_state='running')
    with pytest.raises(ValueError,match='pause_case'):
        build(repo,unit['id'])
    repo.operation_update(unit['id'],execution_state='paused')
    source.write_text('Tampered bytes',encoding='utf-8')
    with pytest.raises(ValueError,match='missing_or_changed'):
        build(repo,unit['id'])


def test_service_restart_preserves_known_cost_and_blocks_inflight_usage(operation_case):
    from src.casefile.accounting import RunAccounting
    from src.casefile.supervisor import recover_previous_workers
    from types import SimpleNamespace
    repo,unit,scope=operation_case
    approve(repo,unit,scope)
    created=task(repo,unit)
    current,run=orquestracao.pegar(repo,unit['id'],'process:worker-dead',teto=50)
    ledger=RunAccounting(repo,current,run)
    ledger.before()
    ledger.response(SimpleNamespace(usage=object(),request_id='confirmed_first'),{'synthetic':True},.2)
    ledger.before()
    recover_previous_workers(repo)
    assert repo.tarefa(created['id'])['status']=='bloqueada'
    assert repo.run(run['id'])['usage_state']=='unknown'
    assert float(repo.run(run['id'])['cost_usd'])==.2
    assert repo.custo_acumulado(unit['id'])==.2
    assert repo.operation_case(unit['id'])['execution_state']=='waiting'
    assert repo.conn.execute('SELECT count(*) AS n FROM operation_requests WHERE status=\'unknown\'').fetchone()['n']==1
    with pytest.raises(ValueError,match='reconcile_provider_usage'):
        operations.command(repo,request(repo,unit,'resume'))


def test_shared_additional_cap_reserves_unknown_usage_and_releases_confirmed(operation_case):
    from src.casefile import spending
    from src.casefile.accounting import RunAccounting,UnknownProviderUsage
    from types import SimpleNamespace
    repo,unit,scope=operation_case
    approve(repo,unit,scope)
    operations.command(repo,request(repo,unit,'pause'))
    spending.approve(repo,[unit['id']],1,'human:test','Additional synthetic cap, not production approval.')
    operations.command(repo,request(repo,unit,'resume'))
    task(repo,unit)
    current,run=orquestracao.pegar(repo,unit['id'],'process:worker-cap',teto=50)
    ledger=RunAccounting(repo,current,run)
    ledger.before(.8)
    assert float(spending.state(repo)['available_usd'])==.2
    with pytest.raises(UnknownProviderUsage):ledger.failure(RuntimeError('synthetic missing response'))
    assert float(spending.state(repo)['available_usd'])==.2
    with pytest.raises(spending.SharedSpendingCap):spending.reserve(repo,unit['id'],.3)
    ledger.response(SimpleNamespace(usage=object(),request_id='late_confirmed'),{'actual':True},.1)
    assert float(spending.state(repo)['available_usd'])==.9
    assert float(spending.state(repo)['known_cost_usd'])==.1


def test_bounded_unknown_blocks_only_affected_task_and_holds_both_budget_reserves(operation_case):
    from src.casefile import spending
    from src.casefile.accounting import RunAccounting,UnknownProviderUsage
    repo,unit,scope=operation_case
    approve(repo,unit,scope)
    operations.command(repo,request(repo,unit,'pause'))
    spending.approve(repo,[unit['id']],1,'human:test','Synthetic additional budget.')
    repo.operation_update(unit['id'],approved_budget_usd=1)
    operations.command(repo,request(repo,unit,'resume'))
    affected=task(repo,unit)
    current,run=orquestracao.pegar(repo,unit['id'],'fixture-unknown',teto=1)
    ledger=RunAccounting(repo,current,run);ledger.before(.8)
    with pytest.raises(UnknownProviderUsage):ledger.failure(RuntimeError('synthetic interrupted response'))
    repo.fechar_run(run['id'],'fixture-unknown',output_json=None,output_valid=False,validation_errors=[],stop_reason='unknown',para='bloqueada')
    operations.command(repo,request(repo,unit,'pause'))
    operations.command(repo,request(repo,unit,'resume'))
    other=task(repo,unit)
    got=orquestracao.pegar(repo,unit['id'],'fixture-other',teto=1,max_active_per_unit=1)
    assert got[0]['id']==other['id']
    assert repo.reservar_orcamento(got[1]['id'],'fixture-other',1)['limite']==.2
    assert float(spending.state(repo)['available_usd'])==.2
    with pytest.raises(ValueError,match='reconcile_usage_before_retry'):
        operations.command(repo,request(repo,unit,'retry_task',task_id=affected['id']))


def test_suspension_expired_lease_does_not_repeat_inflight_request(operation_case):
    from src.casefile import spending
    from src.casefile.accounting import RunAccounting
    repo,unit,scope=operation_case
    approve(repo,unit,scope)
    operations.command(repo,request(repo,unit,'pause'))
    spending.approve(repo,[unit['id']],1,'human:test','Synthetic shared reserve')
    operations.command(repo,request(repo,unit,'resume'))
    affected=task(repo,unit)
    current,run=orquestracao.pegar(repo,unit['id'],'fixture-suspended',teto=50,max_active_per_unit=1)
    ledger=RunAccounting(repo,current,run);ledger.before(.2)
    repo.conn.execute("UPDATE task_runs SET lease_until=now()-interval '1 minute' WHERE id=%s",(run['id'],))
    other=task(repo,unit)
    new=orquestracao.pegar(repo,unit['id'],'fixture-after-suspension',teto=50,max_active_per_unit=1)
    assert new[0]['id']==other['id'] and repo.tarefa(affected['id'])['status']=='bloqueada'
    assert len(repo.runs_da_tarefa(affected['id']))==1
    assert float(spending.state(repo)['reserved_usd'])==.2
    assert repo.conn.execute('SELECT count(*) AS n FROM operation_requests').fetchone()['n']==1


def test_scope_and_budget_cannot_change_during_an_unfinished_run(operation_case):
    repo,unit,scope=operation_case
    approve(repo,unit,scope)
    task(repo,unit)
    orquestracao.pegar(repo,unit['id'],'process:worker-test',teto=50)
    with pytest.raises(ValueError,match='pause_and_wait'):
        operations.command(repo,request(repo,unit,'start',budget_usd=40,scope=scope))


def test_exclusive_browser_resource_and_independent_pid(operation_case):
    repo,unit,scope=operation_case
    assert repo.operation_resource('browser','worker-a',60)
    assert not repo.operation_resource('browser','worker-b',60)
    assert repo.operation_resource('different-browser','worker-b',60)
    repo.operation_release_resource('browser','worker-b')
    assert not repo.operation_resource('browser','worker-b',60)
    repo.operation_release_resource('browser','worker-a')
    assert repo.operation_resource('browser','worker-b',60)


def test_report_change_invalidates_verified_requirements(operation_case):
    repo,unit,scope=operation_case
    repo.operation_requirement_record(unit['id'],'a'*64,'Q3','verified',{'receipt':'synthetic'},'human:test')
    repo.operation_report_requirements(unit['id'],'b'*64)
    old=repo.operation_requirements(unit['id'],'a'*64)
    assert next(q for q in old if q['criterion']=='Q3')['status']=='invalidated'
    assert all(q['status']=='pending' for q in repo.operation_requirements(unit['id'],'b'*64))


def test_inventory_is_resumable_preserves_state_and_bytes(operation_case):
    from src.casefile.bootstrap import inventory
    repo,unit,scope=operation_case
    workspace=Path(unit['folder_path']).parent
    Path(unit['folder_path']).mkdir(parents=True,exist_ok=True)
    source=Path(unit['folder_path'])/'synthetic.pdf'
    source.write_bytes(b'synthetic inventory bytes; not a legal instrument')
    before=digest_file(source)
    first=inventory(repo,workspace,[unit])
    count=len(repo.operation_artifacts(unit['id']))
    assert inventory(repo,workspace,[unit])==first
    assert len(repo.operation_artifacts(unit['id']))==count
    assert len(repo.tarefas(unit['id']))==1
    assert repo.tarefas(unit['id'])[0]['status']=='aceita'
    assert repo.estado_da_unit(unit['id'])=='INDICADA'
    assert digest_file(source)==before
    assert repo.custo_acumulado(unit['id'])==0


def test_followups_wait_for_allocation_instead_of_disappearing(operation_case):
    repo,unit,scope=operation_case
    repo.operation_update(unit['id'],approved_budget_usd=1)
    first=task(repo,unit,budget=1)
    repo.operation_enqueue(unit['id'],'deferred-review','verificador','Review',{},'extracao_cega',.6)
    assert repo.operation_allocate(unit['id'])==[]
    assert len(repo.operation_followups(unit['id']))==1
    repo.transicionar_tarefa(first['id'],('pronta',),'cancelada','human:test','Release allocation')
    assert len(repo.operation_allocate(unit['id']))==1
    assert repo.operation_followups(unit['id'])==[]
