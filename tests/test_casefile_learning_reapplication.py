import pytest
from tests.test_casefile_operations import operation_case,approve,task,request
from tests.helpers_casefile import ClientRoteirizado,Use
from src.casefile import operations,worker,learning,runtime,training
from src.casefile.storage import digest_file


def test_new_approved_lesson_matches_canonical_project_and_is_applied_in_next_session(operation_case,tmp_path,monkeypatch):
    from tests.test_casefile_training import card
    from src.casefile import training_runtime
    repo,unit,scope=operation_case
    store=training.Store(tmp_path/'scope-store');monkeypatch.setattr(learning,'Store',lambda:store)
    base=card(tmp_path,project='land_cibola_surface_title');base['scope']['substance']=['surface'];base['scope']['work_type']=['surface_title']
    first=store.put(base)
    rid=store.publish([{'rule_id':first['rule_id'],'version':first['version']}],reviewer='human:fixture',reason='Synthetic scope',reviewed_at='2026-10-12')
    context={k:v[0] for k,v in base['scope'].items()}
    repo.configure_training(unit['id'],{'release_id':rid,'scope':context,'store_root':str(store.root),'reviewer':'human:fixture','reason':'Synthetic scope'})
    approve(repo,unit,scope)
    src=base['sources'][0]
    artifact=repo.operation_add_artifact(unit['id'],'run_record',src['path'],src['sha256'],len(src['quote']))
    retro=task(repo,unit,'retrospectivo','fichas_candidatas',mode='obrigatoria_e_operador')
    sid=repo.abrir_sessao(unit['id'],'tarefa:retrospectivo','fixture');training_runtime.prepare(repo,unit,sid,'tarefa:retrospectivo',store)
    output={'fichas':[{'type':'Lesson','title':'Synthetic scope','description':'Method only','status':'draft','funcao':'retrospectivo',
        'escopo':{'pacote':'title-texas-surface'},'destino':'pacote','regra':'Synthetic approved method','interpretacao':'Synthetic method only',
        'sources':[{'artifact_id':artifact['id'],'resource':'fixture','id':str(artifact['id']),'locator':'line:1','quote':src['quote']}]}],'fatos_da_unit':[]}
    learning.persist(repo,retro,output,sid)
    lesson=repo.operation_lessons(unit['id'])[0]
    assert lesson['card']['scope']['project']==['land_cibola_surface_title']
    learning.verify(repo,lesson['id'],{'source_quotes_confirmed':True,'methodology_only':True,'reason':'Synthetic independent source review'},actor='process:fixture',model_family='B')
    learning.review_batch(repo,unit['id'],[lesson['id']],True,'human:fixture','Synthetic explicit approval')
    next_sid=repo.abrir_sessao(unit['id'],'tarefa:examinador','fixture')
    _,_,dispatch=training_runtime.prepare(repo,unit,next_sid,'tarefa:examinador',store)
    found=dispatch['consultar_training']('Synthetic approved method')
    assert any(c['version']==lesson['version'] for c in found['cards'])
    dispatch['aplicar_training'](lesson['card']['rule_id'],lesson['version'],'Synthetic application',[],'none','fixture')
    assert any(e['kind']=='applied' and e['session_id']==next_sid and e['detail']['version']==lesson['version'] for e in repo.knowledge_audit(unit['id'])['events'])


def test_failed_learning_application_reuses_paid_output_and_keeps_failed_history(operation_case,tmp_path,monkeypatch):
    repo,unit,scope=operation_case
    approve(repo,unit,scope)
    store=training.Store(tmp_path/'training');monkeypatch.setattr(learning,'Store',lambda:store)
    path=tmp_path/'method.txt';quote='Use bounded windows after repeated context growth.';path.write_text(quote,encoding='utf-8')
    artifact=repo.operation_add_artifact(unit['id'],'run_record',path,digest_file(path),path.stat().st_size)
    proposed={'type':'Lesson','title':'Synthetic bounded context','description':'Synthetic method only.','status':'draft','funcao':'examinador',
        'escopo':{'pacote':'title-texas-surface'},'destino':'pacote','regra':quote,'interpretacao':'Fixture only.',
        'sources':[{'artifact_id':artifact['id'],'resource':'local','id':str(artifact['id']),'locator':'line:1','quote':quote}]}
    output={'fichas':[proposed],'fatos_da_unit':[]}
    retro=task(repo,unit,'retrospectivo','fichas_candidatas',mode='obrigatoria_e_operador')
    original=repo.knowledge_event
    def broken(uid,sid,kind,data):
        if kind=='candidate_written':raise ValueError('synthetic_storage_failure')
        return original(uid,sid,kind,data)
    monkeypatch.setattr(repo,'knowledge_event',broken)
    result=worker.executar_uma(repo,unit['id'],'fixture',teto=50,operation=True,client=ClientRoteirizado([[Use('entregar_saida',{'saida':output})]]))
    failed=repo.run(result['run_id']);assert failed['stop_reason']=='result_not_persisted'
    assert not repo.operation_lessons(unit['id'])
    with pytest.raises(ValueError,match='applied_before_acceptance'):
        operations.command(repo,request(repo,unit,'decide_task',task_id=retro['id'],accept=True))
    monkeypatch.setattr(repo,'knowledge_event',original)
    cost=repo.custo_acumulado(unit['id'])
    cmd=request(repo,unit,'apply_preserved_result',run_id=result['run_id'])
    first=operations.command(repo,cmd);assert operations.command(repo,cmd)==first
    operations.command(repo,request(repo,unit,'apply_preserved_result',run_id=result['run_id']))
    assert repo.run(result['run_id'])==failed
    assert repo.custo_acumulado(unit['id'])==cost and len(repo.runs_da_tarefa(retro['id']))==1
    assert len(repo.operation_lessons(unit['id']))==1
    assert repo.tarefa(retro['id'])['status']=='aguardando_verificacao'
    lesson=repo.operation_lessons(unit['id'])[0]
    learning.verify(repo,lesson['id'],{'source_quotes_confirmed':False,'methodology_only':True,'reason':'Synthetic unsupported interpretation'},actor='process:fixture',model_family='B')
    assert repo.operation_lessons(unit['id'])[0]['status']=='candidate'
    with pytest.raises(ValueError,match='unverified'):
        learning.review_batch(repo,unit['id'],[lesson['id']],True,'human:fixture','Fixture only.')
