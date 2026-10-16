"""Application services for the local agent workbench; no title inference."""
from __future__ import annotations

import json
import os
import re
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from src.casefile import agentes, orquestracao
from src.casefile.storage import checked_artifact, operation_root
from src.casefile.training import digest

ACTOR='human:renato'
PACK='title-texas-surface'
ROLE_NAMES={
    'coordenador':'Coordenador','pesquisador':'Pesquisador','arquivista':'Arquivista',
    'classificador':'Classificador','examinador':'Examinador','verificador':'Verificador',
    'arbitro':'Árbitro','redator':'Redator','qa_pacote':'Qualidade','retrospectivo':'Aprendizado'}
ROLE_STAGES={'coordenador':'Planejamento','pesquisador':'Pesquisa','arquivista':'Documentos',
             'classificador':'Classificação','examinador':'Exame','verificador':'Revisão independente',
             'arbitro':'Divergências','redator':'Relatório','qa_pacote':'Qualidade','retrospectivo':'Conhecimento'}


class OperationConflict(ValueError):
    pass


def serializable(value):
    return json.loads(json.dumps(value,default=str,ensure_ascii=False))


def require_human(actor,note):
    if not re.fullmatch(r'human:[\w.-]+',str(actor or '')) or not str(note or '').strip():
        raise ValueError('explicit_human_decision_required')


def has_unbounded_usage(repo,unit_id):
    return bool(repo.conn.execute(
        "SELECT 1 FROM task_runs r JOIN tasks t ON t.id=r.task_id WHERE t.unit_id=%s "
        "AND (r.usage_state='unknown' OR (r.finished_at IS NOT NULL AND EXISTS (SELECT 1 FROM operation_requests q WHERE q.run_id=r.id AND q.status='inflight'))) "
        "AND (NOT EXISTS (SELECT 1 FROM operation_requests q WHERE q.run_id=r.id AND q.status IN ('unknown','inflight')) "
        "OR EXISTS (SELECT 1 FROM operation_requests q WHERE q.run_id=r.id AND q.status IN ('unknown','inflight') AND q.reserved_usd<=0)) LIMIT 1",
        (unit_id,)).fetchone())


def require_running(repo,unit_id):
    case=repo.operation_case(unit_id)
    if not case or case['execution_state']!='running':
        raise ValueError('execution_not_running')
    if float(case['approved_budget_usd'])<=0 or not case['approval'].get('actor'):
        raise ValueError('budget_not_approved')
    if has_unbounded_usage(repo,unit_id):
        raise ValueError('provider_usage_requires_reconciliation')
    return case


def roles():
    return [{'id':key,'name':value,'stage':ROLE_STAGES[key]} for key,value in ROLE_NAMES.items()]


def preflight(repo,unit_id):
    case=repo.operation_case(unit_id)
    if not case:
        raise ValueError('operation_case_not_registered')
    from src.casefile import project_profile, verificador
    from src.casefile.worker import MODELO_POR_NIVEL
    from src.infra.loop import RATES
    unit=next(u for u in repo.listar_units() if u['id']==unit_id)
    checks=[]
    try:
        profile=project_profile.selected(repo,unit)
        checks.append({'name':'Perfil Cibola','ok':bool(profile),'detail':'Fontes e identidade conferidas' if profile else 'Configurar perfil'})
    except (ValueError,OSError) as exc:
        checks.append({'name':'Perfil Cibola','ok':False,'detail':str(exc)})
    terminal = case['profile'].get('execution_backend') == 'terminal'
    if terminal:
        from src.infra.terminal import auth_status
        checks.extend({'name': label, **auth_status(family)} for family,label in [('A','Claude Code'),('B','Codex / ChatGPT')])
    for variable,label in ([] if terminal else [('ANTHROPIC_API_KEY','Claude'),('OPENAI_API_KEY','OpenAI')]):
        checks.append({'name':label,'ok':bool(os.environ.get(variable)), 'detail':'Credencial configurada' if os.environ.get(variable) else 'Credencial ausente'})
    models={**MODELO_POR_NIVEL,'independente':verificador.modelo_b()}
    proof=operation_root()/'servico'/'provedores.json'
    available=json.loads(proof.read_text('utf-8')) if proof.exists() else {}
    verified=available.get('models')==models and all(available.get('available',{}).get(k) for k in models)
    if not terminal:
        checks.append({'name':'Modelos e tarifas','ok':verified and all(m in RATES for m in models.values()),'detail':'Catálogos conferidos sem inferência paga em '+str(available.get('verified_at')) if verified else 'Conferir disponibilidade nos provedores','models':models})
    checks.append({'name':'Template e exemplar','ok':bool(case['profile'].get('template_artifact_id') and case['profile'].get('lead_example_artifact_id')),'detail':'Selecionados pelo operador' if case['profile'].get('lead_example_artifact_id') else 'Confirmar exemplar vigente de Derek e template antes da escrita'})
    checks.append({'name':'Orçamento','ok':float(case['approved_budget_usd'])>0,'detail':'Aprovação registrada' if float(case['approved_budget_usd'])>0 else 'Nenhum gasto autorizado'})
    checks.append({'name':'Escopo temporal','ok':bool(case['scope'].get('through_date')),'detail':case['scope'].get('through_date') or 'Definir through date'})
    return checks


def snapshot(repo):
    if not repo.operations_installed():
        return {'installed':False,'cases':[],'roles':roles(),'services':[],'last_event_id':0}
    cases=[]
    for case in repo.operation_cases():
        uid=case['unit_id']
        tasks=repo.tarefas(uid)
        sources=repo.operation_sources(uid)
        artifacts=repo.operation_artifacts(uid)
        summaries=[{'id':t['id'],'title':t['title'],'role':t['role'],'status':t['status'],
                    'unit_id':uid,'updated_at':t['updated_at']} for t in tasks]
        cases.append({**case,'cost_usd':repo.custo_acumulado(uid),'task_counts':dict(Counter(t['status'] for t in tasks)),
                      'artifact_counts':dict(Counter(a['kind'] for a in artifacts)),
                      'open_research':sum(r['status']=='aberta' for r in repo.pesquisas(uid)),
                      'external_dependencies':sum(j['status']=='blocked' for j in sources),
                      'tasks':summaries,'pid':case['scope'].get('pid','')})
    from src.casefile.spending import state as shared_spending
    return serializable({'installed':True,'cases':cases,'roles':roles(),'services':repo.operation_services(),'shared_spending':shared_spending(repo),
                         'last_event_id':repo.operation_last_event(),'workers':4})


def detail(repo,unit_id):
    case=repo.operation_case(unit_id)
    if not case:
        raise ValueError('operation_case_not_registered')
    knowledge={}
    decisions=[d for d in repo.decisoes_da_unit(unit_id) if d['kind']=='training_scope' and d['answer'] and d['decided_at']]
    if decisions:
        from src.casefile.training import Store,ROOT
        config=json.loads(decisions[-1]['answer'])
        try:
            approval,cards=Store(config.get('store_root',ROOT)).release(config['release_id'])
            knowledge={'release_id':config['release_id'],'scope':config['scope'],'approval':approval,'cards':cards}
        except (ValueError,OSError) as exc:
            knowledge={'release_id':config['release_id'],'error':str(exc)}
    from src.casefile.knowledge_registry import overview as knowledge_versions
    return serializable({'case':case,'knowledge':knowledge,'knowledge_registry':knowledge_versions(repo),'tasks':repo.tarefas(unit_id),'artifacts':repo.operation_artifacts(unit_id),
                         'research':repo.pesquisas(unit_id),'source_jobs':repo.operation_sources(unit_id),
                         'followups':repo.operation_followups(unit_id),
                         'uncertain_requests':repo.conn.execute("SELECT q.*,t.title,t.id AS task_id FROM operation_requests q JOIN task_runs r ON r.id=q.run_id JOIN tasks t ON t.id=r.task_id WHERE t.unit_id=%s AND (q.status='unknown' OR (q.status='inflight' AND (r.finished_at IS NOT NULL OR r.lease_until<now()))) ORDER BY q.id",(unit_id,)).fetchall(),
                         'requirements':repo.operation_requirements(unit_id),'lessons':repo.operation_lessons(unit_id),
                         'decisions':repo.escalonamentos(unit_id),'proposals':repo.propostas(unit_id),
                         'claims':repo.claims_da_unit(unit_id),'training':repo.knowledge_audit(unit_id),
                         'events':repo.operation_events(unit_id=unit_id,limit=1000,latest=True),'preflight':preflight(repo,unit_id)})


def task_detail(repo,task_id):
    task=repo.tarefa(task_id)
    if not task:
        raise ValueError('task_not_found')
    revision=repo.operation_case(task['unit_id'])['revision']
    runs=repo.runs_da_tarefa(task_id)
    from src.casefile import function_files
    return serializable({'task':task,'case_revision':revision,'runs':runs,'artifacts':[a for a in repo.operation_artifacts(task['unit_id']) if a['task_id']==task_id],
                         'function_files':repo.function_files(task_id=task_id),
                         'lifecycle':[function_files.lifecycle(repo,r['id']) for r in runs],
                         'terminal_calls':repo.conn.execute('SELECT c.* FROM operation_terminal_calls c JOIN task_runs r ON r.id=c.run_id WHERE r.task_id=%s ORDER BY c.id',(task_id,)).fetchall(),
                         'claims':[repo.claim(cid) for cid in repo.claims_da_tarefa(task_id)],
                         'events':repo.operation_events(unit_id=task['unit_id'],limit=1000,task_id=task_id),
                         'training':[c for c in repo.knowledge_audit(task['unit_id'])['contexts']
                                     if c['session_id'] in [r.get('operation_session_id') for r in runs]]})


def seed_coordinator(repo,unit_id,budget):
    existing=[t for t in repo.tarefas(unit_id) if t['role']=='coordenador' and t['status'] not in ('recusada','cancelada','aceita')]
    if existing:
        return existing[0]
    case=repo.operation_case(unit_id)
    orquestracao.registrar_versoes(repo)
    role=next(f for f in agentes.carregar() if f.tipo=='Role' and f.nome=='coordenador')
    task={
        'ref':'operacao-coordenador-'+str(case['revision']),'role':'coordenador','pack':PACK,
        'title':'Organizar o trabalho restante deste tract','output_schema':role.front['saida_esquema'],
        'acceptance':'Cobrir as pendências atuais; usar apenas escopo, fontes e orçamento aprovados.',
        'input_json':{'operation':True,'scope':case['scope'],'operation_revision':case['revision']},
        'budget_usd':min(8.0,float(budget)),'verificacao':'operador','depends_on_refs':[],
        'priority':0,'pendencias':[]}
    created=repo.criar_tarefas(unit_id,[task],'process:operacao')[0]
    repo.promover_prontas(unit_id,'process:operacao')
    return created


def validate_scope(scope):
    if scope.get('work_type')!='surface_title' or not scope.get('through_date'):
        raise ValueError('surface_scope_and_through_date_required')
    start=datetime.fromisoformat(scope.get('start_date','1966-01-01'))
    end=datetime.fromisoformat(scope['through_date'])
    if end<start:
        raise ValueError('invalid_scope_interval')
    if not isinstance(scope.get('sources'),list) or not scope['sources']:
        raise ValueError('approved_sources_required')
    if set(scope['sources'])-{'local','drive','countyrecords','texasfile','rrc','cad','pacer','sos'}:
        raise ValueError('unknown_source')
    return scope


def command(repo,body,actor=ACTOR):
    require_human(actor,body.get('note'))
    cid=str(body.get('command_id',''))
    if not re.fullmatch(r'[A-Za-z0-9_-]{12,100}',cid):
        raise ValueError('command_id_required')
    uid=int(body['unit_id'])
    signature=digest({'actor':actor,'body':body})
    with repo.transacao():
        # Serializes duplicate commands as well as competing case decisions.
        case=repo.operation_case(uid,lock=True)
        if not case:
            raise ValueError('operation_case_not_registered')
        old=repo.operation_command(cid)
        if old:
            if old['body_sha256']!=signature:
                raise OperationConflict('command_id_reused_with_different_body')
            return old['response']
        if int(body.get('expected_revision',-1))!=case['revision']:
            raise OperationConflict('case_changed_refresh_before_deciding')
        action=body.get('action')
        if action=='start':
            if repo.conn.execute('SELECT 1 FROM task_runs r JOIN tasks t ON t.id=r.task_id WHERE t.unit_id=%s AND r.finished_at IS NULL LIMIT 1',(uid,)).fetchone():
                raise ValueError('pause_and_wait_before_scope_or_budget_change')
            scope=validate_scope({**case['scope'],**body.get('scope',{}),'status':'approved'})
            budget=float(body.get('budget_usd',0))
            if not math.isfinite(budget) or budget<=0 or budget>50:
                raise ValueError('explicit_budget_between_zero_and_50_required')
            if budget<=repo.custo_acumulado(uid):
                raise ValueError('approved_budget_has_no_remaining_balance')
            approval={'actor':actor,'note':body['note'],'at':datetime.now(timezone.utc).isoformat(),
                      'scope_sha256':digest(scope),'budget_usd':budget,'command_id':cid}
            repo.operation_update(uid,scope=scope,approved_budget_usd=budget,approval=approval,execution_state='running')
            seed_coordinator(repo,uid,budget-repo.custo_acumulado(uid))
        elif action=='pause':
            repo.operation_update(uid,execution_state='paused')
        elif action=='configure':
            if case['execution_state']=='running':
                raise ValueError('pause_before_profile_change')
            if repo.conn.execute('SELECT 1 FROM task_runs r JOIN tasks t ON t.id=r.task_id WHERE t.unit_id=%s AND r.finished_at IS NULL LIMIT 1',(uid,)).fetchone():
                raise ValueError('wait_current_execution_before_profile_change')
            profile=body.get('profile',{})
            allowed={'template_artifact_id','lead_example_artifact_id','sample_cells','sample_data_clearance',
                     'source_recipes','drive_folder_id','delivery_structure','model_policy'}
            if set(profile)-allowed:
                raise ValueError('unsupported_profile_setting')
            if profile.get('model_policy') and profile['model_policy'] not in ('economic','default'):
                raise ValueError('unknown_model_policy')
            for key in ('template_artifact_id','lead_example_artifact_id'):
                if profile.get(key) and int(profile[key]) not in {a['id'] for a in repo.operation_artifacts(uid)}:
                    raise ValueError('template_or_example_outside_case')
            repo.operation_update(uid,profile={**case['profile'],**profile,'configured_by':actor,'configuration_note':body['note']})
        elif action=='resume':
            if not case['approval'] or float(case['approved_budget_usd'])<=0:
                raise ValueError('initial_approval_required')
            if has_unbounded_usage(repo,uid):
                raise ValueError('reconcile_provider_usage_before_resume')
            repo.operation_update(uid,execution_state='running')
        elif action=='decide_task':
            tid=int(body['task_id'])
            task=repo.tarefa(tid)
            if not task or task['unit_id']!=uid:
                raise ValueError('task_outside_case')
            if body.get('expected_run_id') is not None:
                runs=repo.runs_da_tarefa(tid)
                if not runs or int(body['expected_run_id'])!=runs[-1]['id']:
                    raise OperationConflict('task_result_changed_refresh_before_deciding')
            if body.get('accept') is True:
                runs=repo.runs_da_tarefa(tid)
                latest=runs[-1] if runs else None
                applied=latest and any(e['detail'].get('run_id')==latest['id'] and e['kind'] in ('task.persisted','result.reapplied')
                    for e in repo.operation_events(unit_id=uid,task_id=tid,limit=1000))
                if not applied:raise ValueError('result_must_be_applied_before_acceptance')
                if task['output_schema']=='fichas_candidatas':raise ValueError('knowledge_requires_independent_review_and_human_batch')
                if task['verificacao'] in ('obrigatoria','obrigatoria_e_operador') and task['status']!='aguardando_operador':
                    raise ValueError('independent_review_required_before_material_acceptance')
            if task['role']=='coordenador':
                from src.casefile.runtime import decide_plan
                decide_plan(repo,task,body.get('accept') is True,actor,body['note'])
            else:
                orquestracao.decidir(repo,tid,aceitar=body.get('accept') is True,ator=actor,nota=body['note'])
            repo.promover_prontas(uid,'process:operacao')
        elif action=='requirement':
            artifact=repo.operation_artifact(int(body['report_artifact_id']))
            if not artifact or artifact['unit_id']!=uid or artifact['kind']!='working_report':
                raise ValueError('current_report_required')
            checked_artifact(artifact)
            criterion=body['criterion']
            if criterion not in ['Q'+str(n) for n in range(1,7)]:
                raise ValueError('unknown_submission_criterion')
            evidence_artifact=repo.operation_artifact(int(body['evidence_artifact_id']))
            if not evidence_artifact or evidence_artifact['unit_id']!=uid or evidence_artifact['id']==artifact['id']:
                raise ValueError('separate_version_bound_evidence_required')
            checked_artifact(evidence_artifact)
            meta=evidence_artifact['metadata']
            if meta.get('report_sha256')!=artifact['sha256'] or meta.get('criterion')!=criterion:
                raise ValueError('evidence_does_not_cover_report_version')
            repo.operation_requirement_record(uid,artifact['sha256'],criterion,'verified',
                                               {'artifact_id':evidence_artifact['id'],'note':body['note']},actor)
        elif action=='lesson_batch':
            from src.casefile.learning import review_batch
            review_batch(repo,uid,body['lesson_ids'],body.get('accept') is True,actor,body['note'])
        else:
            from src.casefile.operator_actions import apply
            apply(repo,case,body,actor)
        event=repo.operation_event('operator.'+action,actor,{'note':body['note'],'command_id':cid},unit_id=uid)
        result={'ok':True,'unit_id':uid,'revision':repo.operation_case(uid)['revision'],'event_id':event['id']}
        repo.operation_save_command(cid,signature,uid,result)
        return result
