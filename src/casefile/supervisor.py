"""Four independently connected workers. The browser is an exclusive resource."""
from __future__ import annotations
import os
import threading
from datetime import datetime,timezone

from src.casefile.db import connect
from src.casefile.repo import Repo


class Supervisor:
    def __init__(self,workers=4,client_factory=None):
        self.workers=workers
        self.client_factory=client_factory
        self.stop=threading.Event()
        self.threads=[]
        self.guard=None

    def start(self):
        self.guard=connect()
        if not self.guard.execute('SELECT pg_try_advisory_lock(781876,4) AS ok').fetchone()['ok']:
            self.guard.close()
            raise RuntimeError('PLM workbench already running')
        recover_previous_workers(Repo(self.guard))
        self.stop.clear()
        for index in range(self.workers):
            thread=threading.Thread(target=self.loop,args=(index,),daemon=True,name='plm-worker-'+str(index+1))
            thread.start()
            self.threads.append(thread)
        heartbeat=threading.Thread(target=self.heartbeat,daemon=True,name='plm-heartbeat')
        heartbeat.start()
        self.threads.append(heartbeat)
        return self

    def close(self):
        self.stop.set()
        for thread in self.threads:
            thread.join(timeout=5)
        if self.guard:
            self.guard.close()

    def heartbeat(self):
        while not self.stop.is_set():
            try:
                with connect() as conn:
                    repo=Repo(conn)
                    for index,thread in enumerate(self.threads[:self.workers]):
                        if thread.is_alive():
                            repo.operation_heartbeat('worker-'+str(index+1),{'pid':os.getpid(),'workers':self.workers})
            except Exception:
                pass
            self.stop.wait(5)

    def tick(self,index):
        from src.casefile import worker
        with connect() as conn:
            repo=Repo(conn)
            if not repo.operations_installed():
                return False
            if repo.conn.execute("SELECT 1 FROM operation_resources WHERE resource='dispatch_hold' AND lease_until>now()").fetchone():
                return False
            for case in repo.operation_dispatch_cases():
                uid=case['unit_id']
                repo.operation_allocate(uid)
                repo.liberar_leases_vencidos(uid,'process:supervisor')
                from src.casefile.operations import has_unbounded_usage
                if has_unbounded_usage(repo,uid):
                    repo.operation_update(uid,execution_state='waiting')
                    continue
                try:
                    client=self.client_factory(case,index) if self.client_factory else None
                    result=worker.executar_uma(repo,uid,'process:worker-'+str(index+1),
                                               teto=float(case['approved_budget_usd']),operation=True,client=client)
                    if result is not None:
                        repo.operation_update(uid,last_dispatched_at=datetime.now(timezone.utc))
                        return True
                    from src.casefile import rounds
                    latest_round=rounds.current(repo,uid)
                    if latest_round and latest_round['focus_task_id']:
                        # Issue 10: a focused Round runs nothing beyond its
                        # focus; it closes itself when the focus is done.
                        continue
                    if not any(t['status'] in ('pronta','em_execucao') for t in repo.tarefas(uid)):
                        from src.casefile.runtime import add_followup
                        from src.casefile.training import digest
                        tasks=repo.tarefas(uid)
                        production=[t for t in tasks if t['role'] not in ('retrospectivo','coordenador','verificador') and t['output_schema']!='inventario_registrado']
                        if production and not any(t['status']=='planejada' for t in tasks):
                            ref='retro-'+digest([(t['id'],t['status']) for t in production])[:20]
                            add_followup(repo,uid,'retrospectivo','Aprender com o lote encerrado',{'task_ids':[t['id'] for t in production]},'fichas_candidatas',1.0,ref)
                            if any(t['status']=='pronta' for t in repo.tarefas(uid)):
                                return True
                        repo.operation_update(uid,execution_state='waiting')
                        repo.operation_event('case.waiting','process:supervisor',{'reason':'Sem tarefa executável; consulte dependências e decisões.'},unit_id=uid)
                except Exception as exc:
                    if isinstance(exc,ValueError) and str(exc)=='execution_not_running':
                        # Another worker or the operator may have paused this
                        # case since dispatch read its state. This is idle.
                        continue
                    repo.operation_update(uid,execution_state='waiting')
                    repo.operation_event('worker.attention','process:supervisor',{'error':type(exc).__name__,'reason':str(exc)[:500]},unit_id=uid)
                    repo.abrir_escalonamento(uid,None,'execution',str(exc)[:500],['corrigir impedimento','retomar após revisão'])
            return False

    def loop(self,index):
        while not self.stop.is_set():
            try:
                busy=self.tick(index)
            except Exception:
                busy=False
            self.stop.wait(.25 if busy else 2)


def recover_previous_workers(repo):
    """After the service lock is acquired, earlier service workers are gone."""
    if not repo.operations_installed():return
    abandoned=repo.conn.execute("SELECT r.*,t.unit_id FROM task_runs r JOIN tasks t ON t.id=r.task_id JOIN operation_cases o ON o.unit_id=t.unit_id WHERE r.finished_at IS NULL AND r.worker LIKE 'process:worker-%' ORDER BY r.id").fetchall()
    for run in abandoned:
        uid=run['unit_id']
        with repo.transacao():
            repo.operation_case(uid,lock=True)
            uncertain=repo.conn.execute("UPDATE operation_requests SET status='unknown',finished_at=now() WHERE run_id=%s AND status='inflight' RETURNING id",(run['id'],)).fetchall()
            if run.get('execution_backend') == 'terminal':
                repo.conn.execute("UPDATE operation_terminal_calls SET status='interrupted',failure='executor_restarted',finished_at=now() WHERE run_id=%s AND status='running'",(run['id'],))
                repo.conn.execute("UPDATE task_runs SET usage_state='subscription_interrupted' WHERE id=%s",(run['id'],))
            known=repo.conn.execute("SELECT coalesce(sum(cost_usd),0) AS cost FROM operation_requests WHERE run_id=%s AND status='confirmed'",(run['id'],)).fetchone()['cost']
            reason='executor_restarted_usage_requires_reconciliation' if uncertain else 'executor_restarted_before_application'
            if uncertain:
                repo.conn.execute("UPDATE task_runs SET usage_state='unknown' WHERE id=%s",(run['id'],))
            repo.fechar_run(run['id'],run['worker'],output_json=run['output_json'],output_valid=False,
                validation_errors=[reason],stop_reason=reason,para='bloqueada',
                model=run['model'],model_family=run['model_family'],prompt_sha256=run['prompt_sha256'],
                tokens_in=run['tokens_in'],tokens_out=run['tokens_out'],cost_usd=float(known))
            if run['operation_session_id']:
                repo.fechar_sessao(run['operation_session_id'],reason,0,{},None if uncertain else float(known),'')
            repo.operation_update(uid,execution_state='waiting')
            repo.abrir_escalonamento(uid,run['task_id'],'executor_recovery',
                'O serviço reiniciou antes da aplicação da tarefa. Responsável: operação local / Renato. '+
                ('Conferir o recibo da API antes de retomar; o subtotal conhecido foi preservado.' if uncertain else 'Revisar a saída preservada e retomar a tarefa dentro do limite de tentativas.'),
                ['conferir recibo e saída preservada','retomar após revisão'])
            repo.operation_event('executor.recovered','process:supervisor',
                {'run_id':run['id'],'reason':reason,'known_cost_usd':float(known),'uncertain_request_ids':[q['id'] for q in uncertain]},unit_id=uid,task_id=run['task_id'])
