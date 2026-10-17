"""Explicit local operator receipts, recovery and dependencies. No title inference."""
from pathlib import Path
import math

from src.casefile.storage import REPO_ROOT,checked_artifact,write_bytes,digest_file
from src.casefile.repo import _json


def attach_file(repo,uid,path,kind,metadata):
    source=Path(path).resolve()
    if not source.is_relative_to(REPO_ROOT.parent.resolve()) or not source.is_file():
        raise ValueError('evidence_file_must_exist_inside_PLM_workspace')
    sha=digest_file(source)
    target,_=write_bytes(uid,'evidencias/'+sha+source.suffix.lower(),source.read_bytes())
    return repo.operation_add_artifact(uid,kind,target,sha,source.stat().st_size,
                                       {**metadata,'original_path':str(source),'display_name':source.name})


def apply(repo,case,body,actor):
    uid=case['unit_id']
    action=body['action']
    if action=='set_spend_limit':
        from src.casefile.spending import approve
        approve(repo,body['unit_ids'],body['budget_usd'],actor,body['note'])
    elif action=='apply_preserved_result':
        from src.casefile.runtime import reapply_learning
        reapply_learning(repo,uid,int(body['run_id']),actor,body['note'])
    elif action=='build_packet':
        from src.casefile.operation_packet import build
        build(repo,uid)
    elif action=='import_source':
        artifact=attach_file(repo,uid,body['path'],'source',{'recorded_by':actor,'note':body['note'],
            'origin':body.get('locator','local'),'capture_status':'provided_pending_document_review','territorial_application':'pending'})
        repo.registrar_source_file(artifact['sha256'],artifact['size_bytes'])
        if case['approval']:
            from src.casefile.operations import seed_coordinator
            seed_coordinator(repo,uid,float(case['approved_budget_usd'])-repo.custo_acumulado(uid))
    elif action=='attach_evidence':
        report=repo.operation_artifact(int(body['report_artifact_id']))
        reports=repo.operation_artifacts(uid,'working_report')
        if not report or not reports or reports[-1]['id']!=report['id']:
            raise ValueError('latest_report_required')
        checked_artifact(report)
        criterion=body['criterion']
        if criterion not in ['Q'+str(n) for n in range(1,7)]:
            raise ValueError('unknown_submission_criterion')
        evidence=attach_file(repo,uid,body['path'],'requirement_evidence',
            {'report_sha256':report['sha256'],'criterion':criterion,'recorded_by':actor,
             'note':body['note'],'locator':body.get('locator','')})
        if evidence['sha256']==report['sha256']:
            raise ValueError('separate_receipt_required')
        repo.operation_requirement_record(uid,report['sha256'],criterion,'verified',
                                           {'artifact_id':evidence['id'],'note':body['note']},actor)
    elif action=='resolve_dependency':
        issue=next((e for e in repo.escalonamentos(uid,abertos=True) if e['id']==int(body['escalation_id'])),None)
        if not issue:
            raise ValueError('open_case_dependency_required')
        evidence=attach_file(repo,uid,body['path'],'operator_evidence',{'recorded_by':actor,'note':body['note']})
        repo.responder_escalonamento(issue['id'],body['note']+' | artifact:'+str(evidence['id']),actor)
    elif action=='reconcile_usage':
        row=repo.conn.execute('SELECT q.*,r.operation_session_id,r.task_id,t.unit_id,(r.finished_at IS NOT NULL OR r.lease_until<now()) AS abandoned FROM operation_requests q '
            'JOIN task_runs r ON r.id=q.run_id JOIN tasks t ON t.id=r.task_id WHERE q.id=%s FOR UPDATE OF q',
            (int(body['request_id']),)).fetchone()
        if not row or row['unit_id']!=uid or row['status'] not in ('unknown','inflight'):
            raise ValueError('uncertain_case_request_required')
        if row['status']=='inflight' and not row['abandoned']:
            raise ValueError('provider_request_still_running')
        cost=float(body['cost_usd'])
        if not math.isfinite(cost) or cost<0:
            raise ValueError('confirmed_cost_required')
        evidence=attach_file(repo,uid,body['path'],'provider_receipt',{'request_id':row['id'],'recorded_by':actor,'note':body['note']})
        repo.conn.execute("UPDATE operation_requests SET status='confirmed',cost_usd=%s,usage=%s,finished_at=now() WHERE id=%s",
            (cost,_json({'operator_reconciliation':True,'evidence_artifact_id':evidence['id']}),row['id']))
        if cost:
            repo.registrar_custo(uid,'tarefa',cost,{'run_id':row['run_id'],'request_id':row['id'],'confirmed_response':True,'reconciliation':True})
        pending=repo.conn.execute("SELECT 1 FROM operation_requests WHERE run_id=%s AND status IN ('inflight','unknown')",(row['run_id'],)).fetchone()
        total=repo.conn.execute("SELECT coalesce(sum(cost_usd),0) AS amount FROM operation_requests WHERE run_id=%s AND status='confirmed'",(row['run_id'],)).fetchone()['amount']
        repo.conn.execute('UPDATE task_runs SET usage_state=%s,cost_usd=%s WHERE id=%s',('unknown' if pending else 'confirmed',total,row['run_id']))
        if not pending and row['operation_session_id']:
            repo.conn.execute('UPDATE model_sessions SET cost_usd=%s WHERE id=%s',(total,row['operation_session_id']))
    elif action=='retry_task':
        task=repo.tarefa(int(body['task_id']))
        if not task or task['unit_id']!=uid or task['status'] not in ('bloqueada','aguardando_operador','recusada'):
            raise ValueError('affected_case_task_required')
        if repo.task_attempts(task['id'])>=3:
            raise ValueError('two_new_attempts_exhausted_revise_scope_or_input')
        if any(r['usage_state'] in ('unknown','inflight') for r in repo.runs_da_tarefa(task['id'])):
            raise ValueError('reconcile_usage_before_retry')
        reviewed=repo.conn.execute("UPDATE operation_terminal_calls c SET status='interrupted',receipt=c.receipt || %s::jsonb,finished_at=coalesce(c.finished_at,now()) FROM task_runs r WHERE c.run_id=r.id AND r.task_id=%s AND r.finished_at IS NOT NULL AND c.status IN ('running','interrupted') AND NOT (c.receipt ? 'reviewed_by') RETURNING c.id",
            (_json({'reviewed_by':actor,'review_note':body['note']}),task['id'])).fetchall()
        if reviewed:
            repo.operation_event('terminal.retry_reviewed',actor,{'terminal_call_ids':[r['id'] for r in reviewed],'note':body['note']},unit_id=uid,task_id=task['id'])
        repo.transicionar_tarefa(task['id'],(task['status'],),'planejada',actor,body['note'])
        repo.promover_prontas(uid,'process:operacao')
    elif action=='record_open_item':
        # Issue 11: one click turns a Function's observation into an open item.
        from src.casefile.decision_card import record_open_item
        record_open_item(repo,uid,int(body['task_id']),int(body['observation']),actor,body['note'])
    elif action=='replan':
        from src.casefile.operations import seed_coordinator
        if not case['approval']:
            raise ValueError('initial_scope_and_budget_approval_required')
        seed_coordinator(repo,uid,float(case['approved_budget_usd'])-repo.custo_acumulado(uid))
    elif action=='withdraw_lesson':
        from src.casefile.learning import withdraw
        withdraw(repo,uid,int(body['lesson_id']),actor,body['note'])
    else:
        raise ValueError('unknown_operation_action')
