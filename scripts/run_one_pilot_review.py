"""One real independent review under the shared cap; keep the panel available."""
import json
import argparse
from uuid import uuid4
from src.casefile.db import connect
from src.casefile.repo import Repo
from src.casefile import operations,worker

parser=argparse.ArgumentParser()
parser.add_argument('--task',type=int,default=33)
args=parser.parse_args()

with connect() as conn:
    repo=Repo(conn)
    holder='process:review-debug'
    if not repo.operation_resource('dispatch_hold',holder,1200):raise ValueError('dispatch_diagnostic_in_progress')
    try:
        task=repo.tarefa(args.task)
        uid=task['unit_id']
        if task['role']!='verificador' or task['status'] not in ('pronta','bloqueada'):
            raise ValueError('ready_independent_review_required')
        if not __import__('src.casefile.runtime',fromlist=['cited_pages']).cited_pages(task['input_json'].get('pagina')) and task['output_schema']!='revisao_licao':
            raise ValueError('physical_source_page_required_before_paid_review')
        priority=repo.conn.execute('SELECT coalesce(min(priority),0)-1 AS p FROM tasks WHERE unit_id=%s',(uid,)).fetchone()['p']
        repo.conn.execute('UPDATE tasks SET priority=%s WHERE id=%s',(priority,args.task))
        repo.operation_event('task.priority_changed','process:diagnostic',{'reason':'Executar somente a revisão indicada nesta conferência','priority':priority},unit_id=uid,task_id=args.task)
        if task['status']=='bloqueada':
            operations.command(repo,{'command_id':uuid4().hex,'unit_id':uid,'expected_revision':repo.operation_case(uid)['revision'],
                'action':'retry_task','task_id':args.task,'note':'Conferir uma revisão independente real após corrigir o protocolo da API, dentro do limite adicional compartilhado de USD 20.'})
        operations.command(repo,{'command_id':uuid4().hex,'unit_id':uid,'expected_revision':repo.operation_case(uid)['revision'],
            'action':'resume','note':'Executar uma revisão independente rastreada dentro do escopo aprovado e do limite adicional de USD 20.'})
        result=worker.executar_uma(repo,uid,'process:worker-diagnostic',teto=50,operation=True)
        print(json.dumps({'task_id':result['tarefa']['id'],'status':result['tarefa']['status'],'model':result['modelo'],
            'cost_usd':result['custo_usd'],'reason':result['parada'],'errors':result['erros']},ensure_ascii=False))
        print(json.dumps([e['detail'] for e in repo.operation_events(unit_id=uid,task_id=result['tarefa']['id'],kind='model.rejected',limit=1,latest=True)],ensure_ascii=False))
    finally:
        if repo.operation_case(uid)['execution_state']=='running':
            operations.command(repo,{'command_id':uuid4().hex,'unit_id':uid,'expected_revision':repo.operation_case(uid)['revision'],
                'action':'pause','note':'Conferência isolada encerrada; conservar resultados e aguardar retomada do lote dentro do mesmo limite adicional.'})
        repo.operation_release_resource('dispatch_hold',holder)
