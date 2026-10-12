"""Visible candidate verification and human batch publication, never silent learning."""
from __future__ import annotations
import json
import hashlib
from datetime import datetime,timezone
from pathlib import Path

from src.casefile.operations import require_human
from src.casefile.storage import digest_file,checked_artifact,write_bytes
from src.casefile.training import Store,digest,ROOT


def candidate_scope(repo,uid):
    decisions=[d for d in repo.decisoes_da_unit(uid) if d['kind']=='training_scope' and d['answer'] and d['decided_at']]
    context=json.loads(decisions[-1]['answer'])['scope'] if decisions else {}
    # A display name is not the configured project key. Unknown scope stays
    # ineligible instead of silently becoming a project-wide instruction.
    scope={key:([context[key]] if isinstance(context.get(key),str) else context.get(key,[]))
           for key in ('project','jurisdiction','substance','work_type')}
    scope['stage']=['planning','examination']
    return scope


def validate(repo,task,output,**_):
    """Check cited bytes before stopping inference, so a quote can be repaired."""
    from src.casefile.training import text_parts
    available={a['id']:a for a in repo.operation_artifacts(task['unit_id'])}
    errors=[]
    expected=task.get('input_json',{}).get('expected_application')
    if expected:
        run=repo.run(task.get('_operation_run_id'))
        sid=run.get('operation_session_id') if run else None
        recorded=sid and repo.conn.execute("SELECT 1 FROM knowledge_events WHERE unit_id=%s AND session_id=%s AND kind='applied' AND detail->>'rule_id'=%s AND detail->>'version'=%s LIMIT 1",(task['unit_id'],sid,expected['rule_id'],expected['version'])).fetchone()
        if not recorded:errors.append('knowledge_application_not_recorded_consult_and_apply_offered_version')
    for proposed in output['fichas']:
        for source in proposed['sources']:
            artifact=available.get(int(source.get('artifact_id',0)))
            if not artifact:
                errors.append('lesson_requires_case_artifact_source');continue
            try:
                path=checked_artifact(artifact)
                text='\n'.join(t for _,t in text_parts(path))
                if not source.get('quote','').strip() or source['quote'] not in text:
                    errors.append('source_quote_not_found_copy_literal_source_text')
            except (ValueError,OSError):errors.append('lesson_source_changed_or_unavailable')
    return errors


def persist(repo,task,output,session_id,**_):
    errors=validate(repo,task,output)
    if errors:raise ValueError(';'.join(errors))
    uid=task['unit_id']
    available={a['id']:a for a in repo.operation_artifacts(uid)}
    ids=[]
    raw=json.dumps(output,ensure_ascii=False,indent=2).encode()
    path,sha=write_bytes(uid,f"aprendizado/rodada_{task['id']}_{hashlib.sha256(raw).hexdigest()[:12]}.json",raw)
    repo.operation_add_artifact(uid,'retrospective_observation',path,sha,len(raw),{'case_facts_review':'pending','session_id':session_id},task['id'])
    for proposed in output['fichas']:
        sources=[]
        for source in proposed['sources']:
            artifact=available.get(int(source.get('artifact_id',0)))
            if not artifact:
                raise ValueError('lesson_requires_case_artifact_source')
            checked_artifact(artifact)
            quote=source.get('quote','').strip()
            if not quote:
                raise ValueError('lesson_requires_literal_source_quote')
            sources.append({'path':artifact['path'],'sha256':artifact['sha256'],
                            'locator':source.get('locator',source['id']),'quote':quote})
        card={'rule_id':'plm-lesson-'+digest(proposed)[:20],
              'literal':sources[0]['quote'],'interpretation':proposed['regra']+'\n'+proposed['interpretacao'],
              'nature':'methodology','scope':candidate_scope(repo,uid),
              'conditions':proposed.get('condicoes',[]),'exceptions':proposed.get('excecoes',[]),
              'relations':{'role':proposed['funcao'],'pack':proposed['escopo']['pacote']},
              'sources':sources,'author':'process:retrospectivo','status':'candidate'}
        # put checks bytes and literal quotations but does not approve the rule.
        stored=Store().put(card)
        lesson=repo.operation_add_lesson(uid,task['id'],stored['version'],stored)
        ids.append(lesson['id'])
        repo.knowledge_event(uid,session_id,'candidate_written',{'lesson_id':lesson['id'],'version':stored['version']})
    return ids


def verify(repo,lesson_id,verification,*,actor,model_family):
    lesson=next((l for l in repo.operation_lessons() if l['id']==lesson_id),None)
    if not lesson or lesson['status']!='candidate' or model_family!='B':
        raise ValueError('independent_candidate_verification_required')
    if not isinstance(verification.get('source_quotes_confirmed'),bool) or not isinstance(verification.get('methodology_only'),bool) or not verification.get('reason'):
        raise ValueError('candidate_verification_incomplete')
    for source in lesson['card']['sources']:
        if digest_file(source['path'])!=source['sha256']:
            raise ValueError('lesson_source_changed')
    supported=verification['source_quotes_confirmed'] and verification['methodology_only']
    repo.operation_update_lesson(lesson_id,'verified' if supported else 'candidate',verification={**verification,'actor':actor,'family':model_family})


def review_batch(repo,uid,lesson_ids,accept,actor,note):
    require_human(actor,note)
    lessons={l['id']:l for l in repo.operation_lessons(uid)}
    if not lesson_ids or len(set(lesson_ids))!=len(lesson_ids) or any(i not in lessons for i in lesson_ids):
        raise ValueError('invalid_lesson_batch')
    selected=[lessons[i] for i in lesson_ids]
    decision={'actor':actor,'note':note,'at':datetime.now(timezone.utc).isoformat()}
    if not accept:
        for lesson in selected:
            repo.operation_update_lesson(lesson['id'],'rejected',decision=decision)
        finish_retrospective(repo,uid,selected,actor,note)
        return None
    if any(l['status']!='verified' or l['verification'].get('family')!='B' for l in selected):
        raise ValueError('unverified_lesson_cannot_be_published')
    store=Store()
    decisions=[d for d in repo.decisoes_da_unit(uid) if d['kind']=='training_scope' and d['answer'] and d['decided_at']]
    if not decisions:
        raise ValueError('explicit_training_scope_required')
    previous=json.loads(decisions[-1]['answer'])
    from src.casefile.training import applicable
    if any(not any(applicable(l['card'],{**previous['scope'],'stage':stage}) for stage in ('planning','examination')) for l in selected):
        raise ValueError('lesson_scope_incompatible_with_case')
    approval,cards=store.release(previous['release_id'])
    refs={c['rule_id']:{'rule_id':c['rule_id'],'version':c['version']} for c in cards}
    for lesson in selected:
        card=lesson['card']
        store.get(card['rule_id'],card['version'])
        refs[card['rule_id']]={'rule_id':card['rule_id'],'version':card['version']}
    release=store.publish(list(refs.values()),reviewer=actor,reason=note,reviewed_at=decision['at'])
    rid=release
    repo.configure_training(uid,{**previous,'release_id':rid,'reviewer':actor,'reason':note})
    for lesson in selected:
        repo.operation_update_lesson(lesson['id'],'approved',decision=decision,release_id=rid)
    finish_retrospective(repo,uid,selected,actor,note)
    repo.operation_event('knowledge.published',actor,{'release_id':rid,'lesson_ids':lesson_ids},unit_id=uid)
    return rid


def finish_retrospective(repo,uid,selected,actor,note):
    from src.casefile import orquestracao
    for task_id in {l['task_id'] for l in selected if l['task_id']}:
        siblings=[l for l in repo.operation_lessons(uid) if l['task_id']==task_id]
        task=repo.tarefa(task_id)
        if siblings and all(l['status'] in ('approved','rejected') for l in siblings) and task['status'] in ('aguardando_operador','aguardando_verificacao'):
            orquestracao.decidir(repo,task_id,aceitar=any(l['status']=='approved' for l in siblings),ator=actor,nota=note)


def withdraw(repo,uid,lesson_id,actor,note):
    require_human(actor,note)
    lesson=next((l for l in repo.operation_lessons(uid) if l['id']==lesson_id),None)
    if not lesson or lesson['status']!='approved':
        raise ValueError('approved_case_lesson_required')
    decisions=[d for d in repo.decisoes_da_unit(uid) if d['kind']=='training_scope' and d['answer'] and d['decided_at']]
    previous=json.loads(decisions[-1]['answer'])
    store=Store()
    _,cards=store.release(previous['release_id'])
    refs=[{'rule_id':c['rule_id'],'version':c['version']} for c in cards if c['rule_id']!=lesson['card']['rule_id']]
    at=datetime.now(timezone.utc).isoformat()
    rid=store.publish(refs,reviewer=actor,reason=note,reviewed_at=at)
    repo.configure_training(uid,{**previous,'release_id':rid,'reviewer':actor,'reason':note})
    repo.operation_update_lesson(lesson_id,'withdrawn',decision={'actor':actor,'note':note,'at':at},release_id=rid)
