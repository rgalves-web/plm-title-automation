"""Immutable local decision packet; evidence references, never title acceptance."""
from __future__ import annotations
import io
import json
import zipfile
from collections import Counter
from datetime import datetime,timezone
from html import escape

from src.casefile.operations import serializable
from src.casefile.storage import checked_artifact,write_bytes
from src.casefile.training import digest


def build(repo,unit_id):
    case=repo.operation_case(unit_id,lock=True)
    if not case or case['execution_state']=='running':
        raise ValueError('pause_case_before_packet_snapshot')
    if repo.conn.execute('SELECT 1 FROM task_runs r JOIN tasks t ON t.id=r.task_id WHERE t.unit_id=%s AND r.finished_at IS NULL AND r.lease_until>now() LIMIT 1',(unit_id,)).fetchone():
        raise ValueError('wait_current_execution_before_packet_snapshot')
    unit=next(u for u in repo.listar_units() if u['id']==unit_id)
    artifacts=[a for a in repo.operation_artifacts(unit_id) if a['kind']!='operation_packet']
    # Verify exact references without copying the source library into another
    # standing corpus. Only the latest working report is included in the ZIP.
    references=[]
    for a in artifacts:
        actual=checked_artifact(a)
        references.append({**a,'resolved_path':str(actual)})
    tasks=repo.tarefas(unit_id)
    runs=[r for t in tasks for r in repo.runs_da_tarefa(t['id'])]
    requests=repo.conn.execute('SELECT q.* FROM operation_requests q JOIN task_runs r ON r.id=q.run_id JOIN tasks t ON t.id=r.task_id WHERE t.unit_id=%s ORDER BY q.id',(unit_id,)).fetchall()
    reports=[a for a in artifacts if a['kind']=='working_report']
    latest=reports[-1] if reports else None
    events=repo.conn.execute('SELECT * FROM operation_events WHERE unit_id=%s ORDER BY id',(unit_id,)).fetchall()
    metrics={
        'known_cost_usd':repo.custo_acumulado(unit_id),'approved_budget_usd':case['approved_budget_usd'],
        'requests':dict(Counter(q['status'] for q in requests)),
        'tasks':dict(Counter(t['status'] for t in tasks)),
        'new_attempts':sum(max(0,len(repo.runs_da_tarefa(t['id']))-1) for t in tasks),
        'rejected_captures':sum(e['kind']=='capture.rejected' for e in events),
        'operator_commands':sum(e['actor'].startswith('human:') and e['kind'].startswith('operator.') for e in events),
        'operator_time_minutes':None,'operator_time_limitation':'Tempo de interação humana não foi cronometrado nesta rodada.',
        'source_coverage':{'registered_files':len(references),'documentary_completion':None,
            'limitation':'Contagem de arquivos não mede conclusão de pesquisa ou exame.'}}
    from src.casefile.spending import state
    additional_limit=state(repo,unit_id)
    manifest=serializable({'schema':1,'status':'WORKING DRAFT','title_approval':False,
        'external_submission':False,'unit':unit,'operation_case':case,
        'created_at':datetime.now(timezone.utc).isoformat(),'metrics':metrics,'additional_spending_limit':additional_limit,
        'latest_working_report':latest,'artifacts':references,'tasks':tasks,'runs':runs,'api_receipts':requests,
        'claims':repo.claims_da_unit(unit_id),'research':repo.pesquisas(unit_id),
        'source_jobs':repo.operation_sources(unit_id),'decisions':repo.escalonamentos(unit_id),
        'operator_decisions':repo.decisoes_da_unit(unit_id),'requirements':repo.operation_requirements(unit_id),
        'knowledge':repo.knowledge_audit(unit_id),'lessons':repo.operation_lessons(unit_id),'events':events})
    issues=[e for e in manifest['decisions'] if not e.get('respondido_em')]
    jobs=[j for j in manifest['source_jobs'] if j['status']=='blocked']
    rows=''.join('<tr><td>'+escape(t['role'])+'</td><td>'+escape(t['title'])+'</td><td>'+escape(t['status'])+'</td></tr>' for t in tasks)
    dependencies=''.join('<li>'+escape(e['pergunta'])+' · Responsável: Renato</li>' for e in issues)
    dependencies+=''.join('<li>'+escape(j['source'])+': '+escape(j['receipt'].get('reason','Acesso pendente'))+' · Responsável: '+escape(j['owner'])+' · '+escape(j['impact'])+'</li>' for j in jobs)
    html=('<!doctype html><html lang="pt-BR"><meta charset="utf-8"><title>PLM · Pacote de decisão</title>'
          '<style>body{font:15px system-ui;max-width:1000px;margin:48px auto;color:#292033}h1,h2{color:#5f3982}td,th{padding:10px;border-bottom:1px solid #ddd;text-align:left}li{margin:12px 0}</style>'
          '<h1>'+escape(unit['canonical_name'])+'</h1><p>WORKING DRAFT · retrato da operação, versão '+str(case['revision'])+'</p>'
          '<p>Custo conhecido de APIs: US$ '+format(float(metrics['known_cost_usd']),'.4f')+' · teto aprovado: US$ '+format(float(case['approved_budget_usd']),'.2f')+'</p>'
          '<p>Este pacote conserva resultados, pendências e evidências. Não certifica title, Q1–Q6 ou liberação humana.</p>'
          '<h2>Pendências, responsáveis e próxima ação</h2><ul>'+dependencies+'</ul>'
          '<h2>Tarefas</h2><table><tr><th>Função</th><th>Tarefa</th><th>Estado registrado</th></tr>'+rows+'</table>'
          '<h2>Rastreabilidade</h2><p>casefile.json contém referências verificadas por SHA-256, páginas, resultados, revisões, custos e conhecimento. As fontes originais permanecem nos caminhos resolvidos indicados no arquivo.</p></html>')
    raw=json.dumps(manifest,ensure_ascii=False,indent=2).encode()
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as package:
        package.writestr('casefile.json',raw)
        package.writestr('LEIA_PRIMEIRO.html',html.encode())
        if latest:
            package.writestr('WORKING_DRAFT_'+latest['sha256'][:12]+'.xlsx',checked_artifact(latest).read_bytes())
    data=buffer.getvalue()
    with zipfile.ZipFile(io.BytesIO(data)) as verification:
        if verification.testzip() is not None:raise ValueError('packet_roundtrip_failed')
        if verification.read('casefile.json')!=raw:raise ValueError('packet_manifest_changed')
    path,sha=write_bytes(unit_id,f"pacotes/decisao_v{case['revision']}_{digest(manifest)[:12]}.zip",data)
    return repo.operation_add_artifact(unit_id,'operation_packet',path,sha,len(data),
        {'display_name':unit['canonical_name']+' · pacote de decisão WORKING DRAFT.zip',
         'status':'WORKING DRAFT','snapshot_revision':case['revision'],'reference_files_verified':len(references),
         'title_approval':False,'metrics':serializable(metrics)})
